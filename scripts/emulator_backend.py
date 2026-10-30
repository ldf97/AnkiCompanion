"""Disposable local-only integration harness. Never imported by the shipped server."""
from pathlib import Path
import os,sys,json,socket,subprocess,time,threading,atexit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['ANKI_COMPANION_SKIN']='study_companion'
from anki.collection import Collection
from server.main import create_app
from server.models import Event
from fastapi import Body
import uvicorn

root=ROOT/'test-results/cross-device';root.mkdir(parents=True,exist_ok=True)
data=root/'disposable';data.mkdir(exist_ok=True)
log=(root/'native-sync-server.log').open('w')
env=dict(os.environ,SYNC_USER1='fixture:temporary-test-password',SYNC_HOST='127.0.0.1',SYNC_PORT='8767',SYNC_BASE=str(data/'sync'))
proc=subprocess.Popen([sys.executable,'-m','anki.syncserver'],env=env,stdout=log,stderr=subprocess.STDOUT)
atexit.register(proc.terminate)
for _ in range(100):
    try:
        with socket.create_connection(('127.0.0.1',8767),timeout=.1):break
    except OSError:time.sleep(.1)
col=Collection(str(data/'desktop.anki2'))
for i in range(50):
    note=col.new_note(col.models.by_name('Basic'));note['Front']=f'Acceptance card {i+1}';note['Back']='Answer';col.add_note(note,1)
config=col.decks.get_config(1);config['new']['perDay']=100;col.decks.update_config(config)
auth=col.sync_login('fixture','temporary-test-password','http://127.0.0.1:8767/')
col.close_for_full_sync();col.full_upload_or_download(auth=auth,server_usn=None,upload=True);col.reopen(after_full_sync=True)
def answer(count):
    col.sched.reset()
    for _ in range(count):
        card=col.sched.getCard();assert card is not None
        col.sched.answerCard(card,4)
def native_sync():
    result=col.sync_collection(auth,False);assert result.required==result.NO_CHANGES
    col.sched.reset()
api=create_app(data/'companion','emulator-fixture-token')
settings=api.state.store.settings();settings.update(lesson_answers=50,lesson_ms=0,parent_deck_id='1',timezone='UTC',rollover_minute=0,update_repository='')
api.state.store.update_settings(settings)
def report():
    events=[Event(collection_id='primary',revlog_id=r,card_id=c,duration_ms=min(600000,max(t,0))) for r,c,t in col.db.all('SELECT id,cid,time FROM revlog WHERE ease>0')]
    api.state.store.add_events(events,api.state.packs,device_id='desktop-native')
report()
status=dict(phone_ready=False,observer_ready=False,phone_widget30=False,desktop_widget30=False,phone_widget50=False,desktop_widget50=False,phone_finished=False,matched=False,phase=0)
lock=threading.RLock()
def record():
    (root/'acceptance-status.json').write_text(json.dumps(status,indent=2))
record()
@api.get('/test/status')
def read_status():
    with lock:return dict(status)
@api.post('/test/{action}')
def control(action:str,body:dict=Body(default={})):
    with lock:
        key={'phone-ready':'phone_ready','observer-ready':'observer_ready','phone-finished':'phone_finished','observed30':'phone_widget30','observed50':'phone_widget50','desktop30':'desktop_widget30','desktop50':'desktop_widget50'}.get(action)
        if key:status[key]=True
        elif action=='verify-phone':
            expected=dict(reviews=col.db.all('SELECT id,cid,ease,ivl,lastIvl FROM revlog ORDER BY id'),cards=col.db.all('SELECT id,queue,type,due,ivl,reps,lapses FROM cards ORDER BY id'))
            # JSON normalizes tuples to arrays before comparing the exact schedule and revlog.
            expected=json.loads(json.dumps(expected));assert body==expected, 'AnkiDroid and desktop collection differ'
            assert len(expected['reviews'])==50
            assert len({r[1] for r in expected['reviews']})==50, 'A completed card was repeated'
            assert all(r[5]==1 for r in expected['cards']), 'Each of the 50 cards must be answered exactly once'
            status['matched']=True
            (root/'matching-native-collections.json').write_text(json.dumps(expected,indent=2))
        record();return dict(status)
def progress():
    while True:
        time.sleep(1)
        with lock:
            if status['phase']==0 and status['phone_ready'] and status['observer_ready']:
                try:
                    # Both collections completed their initial empty sync. All
                    # subsequent review transfers must be incremental and automatic.
                    count=col.db.scalar('SELECT count(*) FROM revlog WHERE ease>0')
                    if count==0:answer(20)
                    native_sync();report();status['phase']=20;record()
                except Exception as e:
                    (root/'retry.log').open('a').write(type(e).__name__+': '+str(e)+'\n')
            if status['phone_widget30'] and status['desktop_widget30'] and status['phone_finished'] and status['phase']<50:
                try:
                    native_sync()
                    count=col.db.scalar('SELECT count(*) FROM revlog WHERE ease>0')
                    assert count in (30,50),count
                    if count==30:answer(20)
                    native_sync();report();status['phase']=50;record()
                except Exception as e:
                    (root/'retry.log').open('a').write(type(e).__name__+': '+str(e)+'\n')
threading.Thread(target=progress,daemon=True).start()
uvicorn.run(api,host='127.0.0.1',port=8766,log_level='warning')
