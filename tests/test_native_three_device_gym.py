"""Real Anki 26.9.3 local sync-server: PC1 / phone-model / PC2 gym scenario.

The phone replica here is a *native Anki engine*, not an actual Android
process. Existing separate `cross-device` GitHub job tests real AnkiDroid.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from fastapi.testclient import TestClient
from server.main import create_app


def test_real_native_three_device_gym_offline_undo(tmp_path):
    from anki.collection import Collection

    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    env=dict(os.environ,SYNC_USER1='gym:one-time-fixture-password',SYNC_HOST='127.0.0.1',
             SYNC_PORT=str(port),SYNC_BASE=str(tmp_path/'native-sync'))
    server_log=tmp_path/'native-sync-server.log'
    proc=None;cols=[]
    with server_log.open('w') as log:
        try:
            proc=subprocess.Popen([sys.executable,'-m','anki.syncserver'],env=env,stdout=log,stderr=subprocess.STDOUT)
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:
                    if proc.poll() is not None:raise RuntimeError(server_log.read_text())
                    time.sleep(.1)
            else:raise RuntimeError('Anki native test syncserver never opened its socket')

            pc1=Collection(str(tmp_path/'pc1.anki2'));cols.append(pc1)
            deck_ids={name:pc1.decks.id(name) for name in ('Home-PC','Gym-Phone','Second-PC')}
            for deck_name,count in (('Home-PC',20),('Gym-Phone',15),('Second-PC',5)):
                for i in range(count):
                    note=pc1.new_note(pc1.models.by_name('Basic'))
                    note['Front']=f'{deck_name} question {i}'
                    note['Back']='Answer'
                    pc1.add_note(note,deck_ids[deck_name])
            for deck_id in deck_ids.values():
                cfg=pc1.decks.get_config(deck_id)
                cfg['new']['perDay']=100
                pc1.decks.update_config(cfg)
            auth=pc1.sync_login('gym','one-time-fixture-password',f'http://127.0.0.1:{port}/')
            pc1.close_for_full_sync()
            pc1.full_upload_or_download(auth=auth,server_usn=None,upload=True)
            pc1.reopen(after_full_sync=True)
            phone=Collection(str(tmp_path/'phone-model.anki2'));cols.append(phone)
            phone.close_for_full_sync()
            phone.full_upload_or_download(auth=auth,server_usn=None,upload=False)
            phone.reopen(after_full_sync=True)
            pc2=Collection(str(tmp_path/'pc2.anki2'));cols.append(pc2)
            pc2.close_for_full_sync()
            pc2.full_upload_or_download(auth=auth,server_usn=None,upload=False)
            pc2.reopen(after_full_sync=True)

            def sync(col):
                result=col.sync_collection(auth,False)
                assert result.required==result.NO_CHANGES, f'Unexpected native full-sync choice: {result.required}'
                col.sched.reset()
            def study(col,name,count):
                col.decks.select(deck_ids[name])
                col.sched.reset()
                for _ in range(count):
                    card=col.sched.getCard()
                    assert card is not None, f'No card in {name} after completed {count}'
                    col.sched.answerCard(card,4)
            def reviews(col):
                return col.db.all('SELECT id,cid,ease,ivl,lastIvl,time FROM revlog WHERE ease>0 ORDER BY id,cid')
            def schedule(col):
                return col.db.all('SELECT id,queue,type,due,ivl,reps,lapses FROM cards ORDER BY id')
            def report(col,who,override=None):
                rows=reviews(col) if override is None else override
                events=[dict(collection_id='primary',revlog_id=r[0],card_id=r[1],duration_ms=max(0,min(600000,r[5])),
                             rating=r[2],interval=r[3],previous_interval=r[4]) for r in rows]
                response=companion.post('/v1/events',json={'device_id':who,'events':events})
                assert response.status_code==200,response.text
                return events
            def publish(col,who):
                native=companion.get('/v1/state',params={'device_id':who}).json()['native_sync']
                data=dict(device_id=who,label=who,decks=[],collection_id='primary',
                          native_upload_ticket=native['outgoing_ticket'],
                          applied_revision=native['revision'],sync_status='synced',
                          collection_synced_ms=int(time.time()*1000))
                response=companion.post('/v1/snapshots',json=data)
                assert response.status_code==200,response.text

            companion=TestClient(create_app(tmp_path/'companion','gym-test-bearer-token'))
            settings=companion.get('/v1/settings').json()
            settings.update(lesson_answers=40,lesson_ms=0)
            assert companion.put('/v1/settings',json=settings).status_code==200

            study(pc1,'Home-PC',20)
            sync(pc1);report(pc1,'pc1');publish(pc1,'pc1')
            sync(phone);sync(pc2)
            assert len(reviews(phone))==20
            study(phone,'Gym-Phone',15)
            before=reviews(phone)
            assert len(before)==35
            # Phone loses connectivity; native state remains local.
            phone.undo()
            assert len(reviews(phone))==34
            # PC2 studies different cards while gym phone is disconnected.
            study(pc2,'Second-PC',5)
            sync(pc2);report(pc2,'pc2');publish(pc2,'pc2')
            assert len(reviews(pc2))==25
            # Phone reconnects; unsent attempts including the undone one are
            # submitted to the companion server; only active revlog reaches Anki.
            phone_events=[r for r in before if r not in reviews(pc1)]
            assert len(phone_events)==15
            report(phone,'phone-model',phone_events)
            missing=[r for r in phone_events if r not in reviews(phone)]
            assert len(missing)==1
            key=f'primary:{missing[0][0]}:{missing[0][1]}'
            assert companion.post('/v1/events/retract',json={'device_id':'phone-model','ids':[key]}).status_code==200
            sync(phone);publish(phone,'phone-model')
            sync(pc1);sync(pc2)
            assert reviews(pc1)==reviews(phone)==reviews(pc2)
            assert schedule(pc1)==schedule(phone)==schedule(pc2)
            assert len(reviews(pc1))==39
            state=companion.get('/v1/state',params={'device_id':'pc2'}).json()
            assert state['progress']['answers']==40
            assert state['progress']['active_reviews']==39
            assert state['completed'] and state['streak']>=1
            for who in ('pc1','phone-model','pc2'):
                native=companion.get('/v1/state',params={'device_id':who}).json()['native_sync']
                if native['pending']:
                    # Revision receipts must follow the subsequent native sync,
                    # not merely claim sync because an HTTP event arrived.
                    local={'pc1':pc1,'phone-model':phone,'pc2':pc2}[who]
                    sync(local);publish(local,who)
                    assert not companion.get('/v1/state',params={'device_id':who}).json()['native_sync']['pending']
            (tmp_path/'three-device-native-PASS.json').write_text(__import__('json').dumps({
                'pc1_to_phone_to_pc2':True,'offline_undo_streak_preserved':True,
                'native_reviews':39,'accounted_attempts':40,'all_native_schedules_identical':True},indent=2))
        finally:
            for col in cols:
                try:col.close()
                except Exception:pass
            if proc is not None:
                proc.terminate()
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill()
