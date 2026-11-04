"""Reproducible, disposable three-device coordination lab for AnkiCompanion.

Uses the real authenticated FastAPI server over HTTP and isolated SQLite
outboxes for PC1, an Android-shaped phone, and PC2. `NativeHub` is an explicit
*model*, not AnkiWeb. Real native protocol validation runs separately in CI.
No private Anki profile, Android app or production token is accessed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import json
import multiprocessing
import os
import socket
import sqlite3
import threading
import time
from typing import Any

import httpx

TOKEN = 'gym-lab-ephemeral-token-not-production'
COLLECTION = 'primary'


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


class Offline(Exception):
    pass


class NativeConflict(Exception):
    pass


class NativeHub:
    """Persistent schedule model with conservative same-card conflict detection."""
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with connect(path) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cards(card_id INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL, rating INTEGER NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS heads(card_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS applied(event_id TEXT PRIMARY KEY, undone INTEGER NOT NULL DEFAULT 0);
            ''')

    def current_revision(self, card_id: int) -> int:
        with connect(self.path) as db:
            row = db.execute('SELECT revision FROM heads WHERE card_id=?', (card_id,)).fetchone()
            return int(row['revision']) if row else 0

    def sync(self, changes: list[dict[str, Any]]) -> dict[int, tuple[str, int, int]]:
        with self.lock, connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            # Inspect every mutation before applying any. A collision must not
            # partially mutate authoritative native schedule.
            for event in changes:
                rid, card = event['id'], event['card_id']
                known = db.execute('SELECT undone FROM applied WHERE event_id=?', (rid,)).fetchone()
                head = db.execute('SELECT revision FROM heads WHERE card_id=?',(card,)).fetchone()
                version = head['revision'] if head else 0
                if not known and version != event['base_rev'] and not event['undone']:
                    raise NativeConflict(f'Card {card} changed on another device; original collection retained')
                if known and event['undone'] and known['undone']:
                    continue
                if known and not event['undone']:
                    continue
                if event['undone'] and known is None:
                    # A review undone locally before native upload never has
                    # any native scheduling effect to publish.
                    continue
                if event['undone']:
                    active = db.execute('SELECT event_id FROM cards WHERE card_id=?',(card,)).fetchone()
                    if active and active['event_id'] != rid:
                        raise NativeConflict(f'Undo would replace another device\'s review of card {card}')
            for event in changes:
                rid, card = event['id'], event['card_id']
                known = db.execute('SELECT undone FROM applied WHERE event_id=?',(rid,)).fetchone()
                if event['undone']:
                    if known and not known['undone']:
                        db.execute('DELETE FROM cards WHERE card_id=? AND event_id=?',(card,rid))
                        db.execute('UPDATE applied SET undone=1 WHERE event_id=?',(rid,))
                        db.execute('INSERT INTO heads VALUES(?,1) ON CONFLICT(card_id) DO UPDATE SET revision=revision+1',(card,))
                    continue
                if known:
                    continue
                db.execute('INSERT INTO applied(event_id,undone) VALUES(?,0)',(rid,))
                db.execute('INSERT INTO heads VALUES(?,1) ON CONFLICT(card_id) DO UPDATE SET revision=revision+1',(card,))
                head = db.execute('SELECT revision FROM heads WHERE card_id=?',(card,)).fetchone()[0]
                db.execute('INSERT INTO cards VALUES(?,?,?,?) ON CONFLICT(card_id) DO UPDATE SET event_id=excluded.event_id,rating=excluded.rating,revision=excluded.revision',(card,rid,event['rating'],head))
            rows = db.execute('SELECT card_id,event_id,rating,revision FROM cards ORDER BY card_id').fetchall()
            revisions = db.execute('SELECT card_id,revision FROM heads').fetchall()
            db.commit()
            return {int(row['card_id']): (row['event_id'],int(row['rating']),int(row['revision'])) for row in rows}, {int(row['card_id']):int(row['revision']) for row in revisions}

    def schedule(self):
        with connect(self.path) as db:
            return [(int(r['card_id']),r['event_id'],int(r['rating'])) for r in db.execute('SELECT * FROM cards ORDER BY card_id')]


class Device:
    """Independent durable study/outbox client, with an explicit offline switch."""
    def __init__(self,name: str,root: Path,base: str,hub: NativeHub):
        self.name=name;self.base=base;self.hub=hub;self.online=True
        self.path=root/f'{name}.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
        with connect(self.path) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,card_id INTEGER,rating INTEGER,
                    duration INTEGER,undone INTEGER DEFAULT 0,sent INTEGER DEFAULT 0,undo_sent INTEGER DEFAULT 0,
                    base_rev INTEGER DEFAULT 0,native_applied INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS seen(card_id INTEGER PRIMARY KEY,revision INTEGER);
                CREATE TABLE IF NOT EXISTS local_cards(card_id INTEGER PRIMARY KEY,event_id TEXT,rating INTEGER,revision INTEGER);
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
            ''')
        self.http=httpx.Client(base_url=base,headers={'Authorization':'Bearer '+TOKEN},timeout=5)

    def close(self):self.http.close()
    def request(self,method: str,route: str,**kwargs) -> dict:
        if not self.online:raise Offline(f'{self.name} disconnected')
        try:
            response=self.http.request(method,route,**kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError,httpx.TimeoutException) as exc:
            raise Offline(str(exc)) from exc

    def state(self):return self.request('GET','/v1/state',params={'device_id':self.name,'collection_id':COLLECTION})

    def answer(self,card_id: int,idx: int,day_ms: int,rating: int=3,duration: int=6000) -> str:
        key=f'{COLLECTION}:{day_ms+idx*1000}:{card_id}'
        with connect(self.path) as db:
            row=db.execute('SELECT revision FROM seen WHERE card_id=?',(card_id,)).fetchone()
            version=int(row['revision']) if row else 0
            db.execute('INSERT INTO events (id,card_id,rating,duration,base_rev) VALUES (?,?,?,?,?)',(key,card_id,rating,duration,version))
        return key

    def undo(self,event_id: str) -> None:
        with connect(self.path) as db:
            assert db.execute('UPDATE events SET undone=1 WHERE id=?',(event_id,)).rowcount==1

    def unsent(self):
        with connect(self.path) as db:
            return db.execute('SELECT COUNT(*) FROM events WHERE sent=0 OR (undone=1 AND undo_sent=0)').fetchone()[0]

    def upload(self,loss_after_commit=False):
        with connect(self.path) as db:
            pending=db.execute('SELECT * FROM events WHERE sent=0 ORDER BY id LIMIT 1000').fetchall()
            undo=db.execute('SELECT * FROM events WHERE undone=1 AND undo_sent=0 ORDER BY id LIMIT 1000').fetchall()
        if pending:
            payload=[]
            for r in pending:
                _,ts,card=r['id'].split(':')
                payload.append(dict(collection_id=COLLECTION,revlog_id=int(ts),card_id=int(card),duration_ms=r['duration'],rating=r['rating']))
            receipt=self.request('POST','/v1/events',json={'device_id':self.name,'events':payload})
            # Models the TCP connection dropping AFTER the server committed.
            if loss_after_commit:raise Offline('Reply lost after server committed; retry must be idempotent')
            with connect(self.path) as db:
                db.executemany('UPDATE events SET sent=1 WHERE id=?',[(r['id'],) for r in pending])
                if receipt['native_upload_tickets'].get(COLLECTION):
                    db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('ticket',receipt['native_upload_tickets'][COLLECTION]))
        if undo:
            self.request('POST','/v1/events/retract',json={'device_id':self.name,'ids':[r['id'] for r in undo]})
            with connect(self.path) as db:
                db.executemany('UPDATE events SET undo_sent=1 WHERE id=?',[(r['id'],) for r in undo])
        return len(pending),len(undo)

    def native_sync(self):
        if not self.online:raise Offline(f'{self.name} disconnected')
        with connect(self.path) as db:
            pending=[dict(row) for row in db.execute('SELECT * FROM events WHERE native_applied=0 ORDER BY id')]
        updated,revisions=self.hub.sync(pending)
        with connect(self.path) as db:
            db.execute('UPDATE events SET native_applied=1')
            db.execute('DELETE FROM seen')
            db.executemany('INSERT INTO seen VALUES(?,?)',[(card,rev) for card,rev in revisions.items()])
            db.execute('DELETE FROM local_cards')
            db.executemany('INSERT INTO local_cards VALUES(?,?,?,?)',[(card,info[0],info[1],info[2]) for card,info in updated.items()])

    def publish(self):
        state=self.state()
        with connect(self.path) as db:
            ticket=(db.execute("SELECT value FROM meta WHERE key='ticket'").fetchone() or [''])[0]
        # The server rotates the ticket when undo follows answer upload.
        # A cached ticket can therefore be stale: prefer live native state.
        ticket=state['native_sync'].get('outgoing_ticket') or ticket
        prior=state['native_sync']['revision']
        receipt=self.request('POST','/v1/snapshots',json=dict(device_id=self.name,collection_id=COLLECTION,
            label=self.name,applied_revision=prior,native_upload_ticket=ticket,decks=[],sync_status='synced',
            collection_synced_ms=int(time.time()*1000)))
        with connect(self.path) as db:db.execute("DELETE FROM meta WHERE key='ticket'")
        return receipt

    def handoff(self,max_rounds=4):
        if not self.online:return 'offline_study_allowed'
        for round_ in range(max_rounds):
            for _ in range(20):
                if not self.unsent():break
                self.upload()
            if self.unsent():return 'pending_upload'
            try:self.native_sync()
            except NativeConflict:return 'manual_conflict_preserved'
            self.publish()
            native=self.state()['native_sync']
            if not native['pending'] and not native['outgoing_ticket']:
                return 'verified'
        return 'stale_revision_retry'

    def schedule(self):
        with connect(self.path) as db:
            return [(int(r['card_id']),r['event_id'],int(r['rating'])) for r in db.execute('SELECT * FROM local_cards ORDER BY card_id')]


def server_process(root: str,port: int):
    os.environ['ANKI_COMPANION_SKIN']='study_companion'
    from server.main import create_app
    import uvicorn
    uvicorn.run(create_app(Path(root),TOKEN),host='127.0.0.1',port=port,log_level='error')


class GymLab:
    def __init__(self,root: Path):
        self.root=root;root.mkdir(parents=True,exist_ok=True)
        self.hub=NativeHub(root/'native-hub.sqlite3');self.devices={};self.timeline=[]
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        self.ctx=multiprocessing.get_context('spawn')
        self.server=self.ctx.Process(target=server_process,args=(str(root/'companion'),self.port),daemon=True)
        self.base=f'http://127.0.0.1:{self.port}'

    def __enter__(self):
        self.server.start()
        self.wait_ready()
        for name in ('pc1','phone','pc2'):self.devices[name]=Device(name,self.root,self.base,self.hub)
        return self

    def wait_ready(self):
        with httpx.Client(timeout=1) as session:
            for _ in range(100):
                if not self.server.is_alive():raise RuntimeError('Real API server process terminated')
                try:
                    if session.get(self.base+'/health').status_code==200:break
                except (httpx.ConnectError,httpx.ReadTimeout):pass
                time.sleep(.05)
            else:raise RuntimeError('API server did not become ready')

    def restart_server(self):
        self.server.terminate();self.server.join(timeout=5)
        if self.server.is_alive():self.server.kill()
        self.server=self.ctx.Process(target=server_process,args=(str(self.root/'companion'),self.port),daemon=True)
        self.server.start();self.wait_ready()

    def __exit__(self,*args):
        for device in self.devices.values():device.close()
        self.server.terminate();self.server.join(timeout=5)
        if self.server.is_alive():self.server.kill()

    def record(self,step: str,**data):
        self.timeline.append({'step':step,'t':round(time.monotonic(),3),**data})

    def write_report(self):
        report={'scenario':'gym: PC1 → offline phone → PC2 → reconnection, undo and conflicts',
                'server':'real FastAPI over HTTP in separate process',
                'native':'explicit SQLite conflict-aware scheduling simulator, NOT AnkiWeb',
                'devices':list(self.devices),
                'timeline':self.timeline,
                'native_schedule':self.hub.schedule()}
        (self.root/'gym-lab-report.json').write_text(json.dumps(report,indent=2))
        return report


def run_scenario(root: Path):
    with GymLab(root) as lab:
        pc1,phone,pc2=(lab.devices[x] for x in ('pc1','phone','pc2'))
        settings=pc1.request('GET','/v1/settings')
        # Keep the synthetic reviews safely in the past even when CI runs
        # before UTC noon. Anchor the local study-day rollover one hour before
        # the test starts to avoid midnight boundary flakes as well.
        start=datetime.now(timezone.utc)
        rollover=(start.hour*60+start.minute-60)%(24*60)
        settings.update(lesson_answers=10,lesson_ms=0,timezone='UTC',rollover_minute=rollover)
        assert pc1.request('PUT','/v1/settings',json=settings)['lesson_answers']==10
        day=int((start-timedelta(minutes=10)).timestamp()*1000)
        # PC1 answers and publishes, then phone explicitly syncs before study.
        for i in range(1,21):pc1.answer(i,i,day)
        assert pc1.handoff()=='verified'
        assert phone.handoff()=='verified'
        assert len(phone.schedule())==20
        lab.record('PC1 answered 20; phone entered gym with current schedule',count=20)
        # Explicit authenticated long poll across separate TCP clients.
        cursor=pc2.request('GET','/v1/changes')['sequence']
        start=time.monotonic()
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending=executor.submit(pc2.request,'GET','/v1/changes',params={
                'since':cursor,'wait_ms':3500,'device_id':'pc2','collection_id':COLLECTION})
            time.sleep(.05)
            event=pc1.answer(21,21,day)
            pc1.upload()
            change=pending.result(timeout=4)
        notify_seconds=time.monotonic()-start
        assert change['changed'] and notify_seconds<5,(change,notify_seconds)
        # Deliver the newly observed review before switching locations.
        assert pc1.handoff()=='verified'
        assert phone.handoff()=='verified'
        lab.record('Native-scheduling notification from PC1 to PC2',seconds=round(notify_seconds,3))
        # Gym has no cellular service; answering must never require the server.
        phone.online=False
        assert phone.handoff()=='offline_study_allowed'
        offline_reviews=[phone.answer(i,i+50,day) for i in range(22,37)]
        phone.undo(offline_reviews[0])
        assert phone.unsent()==15
        lab.record('Gym went offline, phone answered 15, undid one',queued=15)
        # Phone app is killed by Android while offline, then reopened. Its
        # standalone SQLite outbox must survive process lifetime.
        phone.close()
        phone=lab.devices['phone']=Device('phone',root,lab.base,lab.hub)
        phone.online=False
        assert phone.unsent()==15
        lab.record('Android process restarted offline; 15 queued attempts survived')
        # PC2 independently studies different cards while gym is offline.
        assert pc2.handoff()=='verified'
        for i in range(37,42):pc2.answer(i,i+100,day)
        assert pc2.handoff()=='verified'
        lab.record('PC2 studied while phone disconnected',count=5)
        # Simulated dropped ACK after commit: local outbox MUST survive and
        # retry without a duplicated review, streak count, or native ticket.
        phone.online=True
        try:phone.upload(loss_after_commit=True)
        except Offline:pass
        assert phone.unsent()==15
        recovery_start=time.monotonic()
        assert phone.handoff()=='verified'
        assert pc1.handoff()=='verified'
        assert pc2.handoff()=='verified'
        recovery_seconds=time.monotonic()-recovery_start
        # Purely local model performance—not a 5s AnkiWeb guarantee.
        assert recovery_seconds<5, recovery_seconds
        lab.record('All-device reconnection/reconciliation (local model)',seconds=round(recovery_seconds,3))
        expected=pc1.schedule()
        assert expected==phone.schedule()==pc2.schedule()==lab.hub.schedule()
        assert len(expected)==40, (len(expected),expected)
        state=pc1.state()
        assert state['progress']['answers']==41,state['progress']
        assert state['progress']['active_reviews']==40,state['progress']
        assert state['completed'] and state['streak']>=1
        lab.record('All three native schedules converge',native_active=len(expected),
                   accounted_attempts=state['progress']['answers'],streak=state['streak'])
        # Actual API process restart, not merely a new Store object.
        lab.restart_server()
        restarted=phone.state()
        assert restarted['progress']['answers']==41
        assert restarted['native_sync']['pending'] is False
        assert pc2.state()['native_sync']['pending'] is False
        lab.record('HTTP server process restarted; persistent progress, receipts and authentication survived')
        # Concurrent same-card updates: do not silently overwrite either.
        assert pc1.handoff()=='verified' and pc2.handoff()=='verified'
        conflict1=pc1.answer(90,300,day)
        conflict2=pc2.answer(90,301,day)
        assert pc1.handoff()=='verified'
        assert pc2.handoff()=='manual_conflict_preserved'
        with connect(pc2.path) as db:
            record=db.execute('SELECT native_applied FROM events WHERE id=?',(conflict2,)).fetchone()
            assert record['native_applied']==0
        assert any(row[0]==90 and row[1]==conflict1 for row in lab.hub.schedule())
        assert pc1.state()['progress']['answers']==43 # both attempts acknowledged; conflict still visible
        unresolved=pc2.state()['native_sync']
        assert unresolved['outgoing_ticket'], 'Unsafe: failed native conflict falsely acknowledged'
        lab.record('Simultaneous edit conflict preserved both attempts, did not overwrite remote scheduling')
        result=lab.write_report();result['notification_seconds']=notify_seconds
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('test-results/gym-lab'))
    opts=parser.parse_args()
    opts.output.mkdir(parents=True,exist_ok=True)
    data=run_scenario(opts.output)
    print(json.dumps({'status':'PASS','notification_seconds':round(data['notification_seconds'],3),
        'schedule':len(data['native_schedule']),'events':len(data['timeline']),
        'report':str(opts.output/'gym-lab-report.json')},indent=2))


if __name__=='__main__':main()
