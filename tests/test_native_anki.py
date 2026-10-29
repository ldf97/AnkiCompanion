"""Real Anki backend + local native sync server, NOT AnkiDroid or GUI acceptance."""
import importlib.util, os, socket, sqlite3, subprocess, sys, time
from pathlib import Path
import pytest
from anki.collection import Collection
from fastapi.testclient import TestClient
from server.main import create_app

spec=importlib.util.spec_from_file_location('bridge_history',Path(__file__).resolve().parents[1]/'anki_addon/history.py')
history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)

def queue():
    db=sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE outbox(id TEXT PRIMARY KEY,payload TEXT,sent INTEGER DEFAULT 0);CREATE TABLE undo(id TEXT PRIMARY KEY,sent INTEGER DEFAULT 0);')
    return db

def answer(col,count):
    for _ in range(count):
        card=col.sched.getCard()
        assert card is not None, 'Unexpected empty scheduler'
        col.sched.answerCard(card,4)

def test_actual_anki_review_undo_and_old_import(tmp_path):
    col=Collection(str(tmp_path/'collection.anki2'))
    try:
        for i in range(3):
            note=col.new_note(col.models.by_name('Basic'));note['Front']=str(i);note['Back']='Answer';col.add_note(note,1)
        col.sched.reset();answer(col,2)
        out=queue();cursor=history.reconcile(col.db,out,'primary',0,0)
        assert out.execute('SELECT count(*) FROM outbox').fetchone()[0]==2
        col.undo()
        history.reconcile(col.db,out,'primary',cursor,int(time.time()*1000))
        assert out.execute('SELECT count(*) FROM undo').fetchone()[0]==1
        # An imported older review falls behind the forward cursor.
        col.db.execute('INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?,?)',1000,1,0,4,1,0,2500,1000,0)
        history.reconcile(col.db,out,'primary',0,int(time.time()*1000))
        assert out.execute("SELECT count(*) FROM outbox WHERE id='primary:1000:1'").fetchone()[0]==1
    finally:col.close()

def test_native_collection_sync_20_10_20(tmp_path):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=dict(os.environ,SYNC_USER1='fixture:temporary-test-password',SYNC_HOST='127.0.0.1',SYNC_PORT=str(port),SYNC_BASE=str(tmp_path/'sync-server'))
    with (tmp_path/'native-server.log').open('w') as log:
        proc=subprocess.Popen([sys.executable,'-m','anki.syncserver'],env=env,stdout=log,stderr=subprocess.STDOUT)
        clients=[]
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:
                    assert proc.poll() is None,(tmp_path/'native-server.log').read_text()
                    time.sleep(.1)
            a=Collection(str(tmp_path/'desktop.anki2'));clients.append(a)
            for i in range(50):
                note=a.new_note(a.models.by_name('Basic'));note['Front']=f'Card {i}';note['Back']='Answer';a.add_note(note,1)
            config=a.decks.get_config(1);config['new']['perDay']=100;a.decks.update_config(config)
            auth=a.sync_login('fixture','temporary-test-password',f'http://127.0.0.1:{port}/')
            a.close_for_full_sync();a.full_upload_or_download(auth=auth,server_usn=None,upload=True);a.reopen(after_full_sync=True)
            b=Collection(str(tmp_path/'phone-model.anki2'));clients.append(b)
            b.close_for_full_sync();b.full_upload_or_download(auth=auth,server_usn=None,upload=False);b.reopen(after_full_sync=True)
            c=TestClient(create_app(tmp_path/'companion','temporary-fixture-token'),headers={'Authorization':'Bearer temporary-fixture-token'})
            settings=c.get('/v1/settings').json();settings.update(lesson_answers=50,lesson_ms=0);assert c.put('/v1/settings',json=settings).status_code==200
            def sync(col):
                result=col.sync_collection(auth,False);assert result.required==result.NO_CHANGES
                col.sched.reset()
            def report(col,device):
                events=[dict(collection_id='primary',revlog_id=r,card_id=k,duration_ms=min(600000,max(0,t))) for r,k,t in col.db.all('SELECT id,cid,time FROM revlog WHERE ease>0')]
                assert c.post('/v1/events',json=dict(device_id=device,events=events)).status_code==200
            a.sched.reset();answer(a,20);sync(a);sync(b);report(a,'desktop')
            assert b.db.scalar('SELECT count(*) FROM revlog')==20
            answer(b,10);sync(b);sync(a);report(b,'phone-model');report(a,'desktop')
            state=c.get('/v1/state').json();assert state['progress']['answers']==30
            assert (state['progress']['percent'],state['progress']['remaining'])==(60,20)
            answer(a,20);sync(a);sync(b);report(a,'desktop');report(b,'phone-model')
            state=c.get('/v1/state').json();assert state['progress']['answers']==50 and state['completed']
            assert a.db.all('SELECT id,cid,ease,ivl,lastIvl FROM revlog ORDER BY id')==b.db.all('SELECT id,cid,ease,ivl,lastIvl FROM revlog ORDER BY id')
            assert a.db.all('SELECT id,queue,type,due,ivl,reps,lapses FROM cards ORDER BY id')==b.db.all('SELECT id,queue,type,due,ivl,reps,lapses FROM cards ORDER BY id')
            assert a.db.scalar('SELECT count(*) FROM revlog')==50
            print('Native Anki 26.9.3 collections: 20 -> 30 -> 50, revlog and scheduling converge. Phone modeled by second Anki backend; NOT AnkiDroid.')
        finally:
            for col in clients:
                try:col.close()
                except Exception:pass
            proc.terminate();proc.wait(timeout=15)
