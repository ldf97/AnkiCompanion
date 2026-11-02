from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
import shutil
from zipfile import ZipFile
import json, pytest
from fastapi.testclient import TestClient
from PIL import Image
from server.main import create_app
from companion.rules import study_day, daily_lineup, next_deck

TOKEN='test-token-at-least-16-chars'
NOW=int(datetime(2026,10,29,16,tzinfo=timezone.utc).timestamp()*1000)

@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path,TOKEN,lambda:NOW)
    with TestClient(app,headers={'Authorization':'Bearer '+TOKEN}) as c: yield c

def event(offset=0,duration=30000,card=1):
    return dict(collection_id='primary',revlog_id=NOW-60000+offset,card_id=card,duration_ms=duration)

def test_authentication(client):
    assert client.get('/v1/state',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.get('/v1/state').status_code==200
    assert client.get('/health').json()=={'status':'ok'}

def test_duplicate_reviews_from_two_devices(client):
    events=[event(i,card=i+1) for i in range(10)]
    assert client.post('/v1/events',json={'events':events}).json()['inserted']==10
    assert client.post('/v1/events',json={'events':events}).json()['inserted']==0
    state=client.get('/v1/state').json()
    assert state['completed'] and state['streak']==1
    assert state['progress']['answers']==10 and state['progress']['duration_ms']==300000

def test_completion_needs_both_thresholds(client):
    client.post('/v1/events',json={'events':[event(i,1000,i+1) for i in range(10)]})
    assert not client.get('/v1/state').json()['completed']
    client.post('/v1/events',json={'events':[event(20,290000,20)]})
    assert client.get('/v1/state').json()['completed']

def test_conflicting_batch_rolls_back(client):
    client.post('/v1/events',json={'events':[event()]})
    response=client.post('/v1/events',json={'events':[event(1),event(duration=1)]})
    assert response.status_code==409
    assert client.get('/v1/state').json()['progress']['answers']==1

def test_undo_tombstone_prevents_late_resurrection(client):
    item=event();key=f"primary:{item['revlog_id']}:1"
    client.post('/v1/events/retract',json={'ids':[key]})
    client.post('/v1/events',json={'events':[item]})
    state=client.get('/v1/state').json()
    assert state['progress']['answers']==1  # evidence of study is immutable
    assert state['progress']['active_reviews']==0
    audit=client.get('/v1/events/audit').json()['events']
    assert len(audit)==1 and audit[0]['retracted'] is True

def test_undo_keeps_streak_accountability(client):
    items=[event(i,card=i+1) for i in range(10)]
    client.post('/v1/events',json={'events':items})
    client.post('/v1/events/retract',json={'ids':[f"primary:{items[0]['revlog_id']}:1"]})
    state=client.get('/v1/state').json()
    assert state['completed'] and state['streak']==1
    assert state['progress']['answers']==10
    assert state['progress']['active_reviews']==9

def test_late_offline_yesterday_extends_streak(client):
    items=[event(i,card=i+1) for i in range(10)]
    yesterday=[dict(x,revlog_id=x['revlog_id']-86400000) for x in items]
    client.post('/v1/events',json={'events':items})
    client.post('/v1/events',json={'events':yesterday})
    assert client.get('/v1/state').json()['streak']==2

def test_settings_revision_and_frozen_daily_goal(client):
    current=client.get('/v1/state').json()['settings']
    updated=dict(current,lesson_answers=1,lesson_ms=0)
    assert client.put('/v1/settings',json=updated).status_code==200
    assert client.put('/v1/settings',json=updated).status_code==409
    client.post('/v1/events',json={'events':[event()]})
    state=client.get('/v1/state').json()
    assert state['policy']['lesson_answers']==10 and not state['completed']

def test_timezone_changes_do_not_relabel_existing_history(client):
    client.post('/v1/events',json={'events':[event()]})
    settings=client.get('/v1/state').json()['settings']
    assert client.put('/v1/settings',json=dict(settings,timezone='UTC')).status_code==409

def test_future_invalid_event_rejected(client):
    assert client.post('/v1/events',json={'events':[dict(event(),revlog_id=NOW+400000)]}).status_code==400
    assert client.post('/v1/events',json={'events':[dict(event(),duration_ms=-1)]}).status_code==422

def test_persistence_across_restart(tmp_path):
    first=TestClient(create_app(tmp_path,TOKEN,lambda:NOW),headers={'Authorization':'Bearer '+TOKEN})
    first.post('/v1/events',json={'events':[event()]})
    before=first.get('/v1/state').json()
    second=TestClient(create_app(tmp_path,TOKEN,lambda:NOW),headers={'Authorization':'Bearer '+TOKEN})
    after=second.get('/v1/state').json()
    assert before['lineup']==after['lineup'] and after['progress']['answers']==1

def test_day_rollover_dst_wall_clock():
    ts=lambda text:int(datetime.fromisoformat(text).timestamp()*1000)
    assert study_day(ts('2026-11-01T06:30:00+00:00'),'America/New_York',240)=='2026-10-31'
    assert study_day(ts('2026-11-01T09:00:00+00:00'),'America/New_York',240)=='2026-11-01'
    assert study_day(ts('2026-03-08T07:30:00+00:00'),'America/New_York',240)=='2026-03-07'

def test_subdeck_clearance_natural_order():
    decks=[dict(id=str(i),name=name,new=n,review=r,learning=l) for i,name,n,r,l in
           [(1,'M2',5,1,0),(2,'M2::Deck 10',3,0,0),(3,'M2::Deck 2',2,0,0),(4,'M2::Deck 1',0,1,0)]]
    assert next_deck(decks,'1','new_only')['id']=='3'
    assert next_deck(decks,'1','new_and_reviews')['id']=='4'
    assert next_deck(decks,'404') is None

def test_commands_require_ack_and_expire(tmp_path):
    clock=[NOW];c=TestClient(create_app(tmp_path,TOKEN,lambda:clock[0]),headers={'Authorization':'Bearer '+TOKEN})
    payload=dict(device_id='desktop',action='study',deck_id='123')
    identity=c.post('/v1/commands',json=payload).json()['id']
    assert len(c.get('/v1/commands/desktop').json()['commands'])==1
    assert not c.get('/v1/commands/phone').json()['commands']
    c.post(f'/v1/commands/desktop/{identity}/ack')
    assert not c.get('/v1/commands/desktop').json()['commands']
    c.post('/v1/commands',json=payload);clock[0]+=121000
    assert not c.get('/v1/commands/desktop').json()['commands']

def test_frame_and_fixed_lineup(client):
    before=client.get('/v1/state').json()['lineup']
    response=client.get('/v1/frame.png')
    assert response.status_code==200 and Image.open(BytesIO(response.content)).size==(1100,468)
    assert client.get('/v1/state').json()['lineup']==before

def test_traversal_zip_rejected(client):
    buffer=BytesIO()
    with ZipFile(buffer,'w') as z:
        z.writestr('../escape.txt','bad');z.writestr('skin.json','{}')
    assert client.post('/v1/skins/import',content=buffer.getvalue()).status_code==400

def test_pack_download_immutable_version(client):
    skin=client.get('/v1/state').json()['lineup']
    response=client.get(f"/v1/skins/{skin['skin_id']}/{skin['skin_version']}/pack.zip")
    assert response.status_code==200
    assert client.post('/v1/skins/import',content=response.content).status_code==400

def test_snapshots_choose_device_deck(client):
    settings=client.get('/v1/state').json()['settings']
    client.put('/v1/settings',json=dict(settings,parent_deck_id='1'))
    payload=dict(device_id='phone',label='Phone',decks=[dict(id='1',name='Root',new=1,review=0,learning=0)])
    assert client.post('/v1/snapshots',json=payload).status_code==200
    state=client.get('/v1/state').json()
    assert state['next_decks']['phone']['id']=='1'

def test_switch_skin_immediately_preserves_reviews_and_frozen_goal(client, tmp_path):
    # A private skin has no source assets in the public repository. Make a
    # second valid test pack using the neutral fixture instead.
    skin_dir = tmp_path / 'packs' / 'eren_anki' / '1.0.0'
    shutil.copytree(Path(__file__).resolve().parents[1] / 'skins' / 'study_companion', skin_dir)
    manifest = skin_dir / 'skin.json'
    skin = json.loads(manifest.read_text())
    skin['id'] = 'eren_anki'
    skin['name'] = 'Eren test fixture'
    manifest.write_text(json.dumps(skin))
    client.app.state.packs._cache = None

    original = client.get('/v1/state').json()
    assert original['lineup']['skin_id'] == 'study_companion'
    assert client.post('/v1/events', json={'events': [event()]}).status_code == 200
    before = client.get('/v1/state').json()
    changed = dict(before['settings'], skin_id='eren_anki', skin_version='1.0.0')
    assert client.put('/v1/settings', json=changed).status_code == 200
    after = client.get('/v1/state').json()
    assert after['lineup']['skin_id'] == 'eren_anki'
    assert after['settings']['skin_id'] == 'eren_anki'
    assert after['policy'] == before['policy']
    assert after['progress'] == before['progress']
    assert after['streak'] == before['streak']
    assert after['lineup']['date'] == before['lineup']['date']
    assert client.get('/v1/frame.png').status_code == 200

def test_restart_reuses_token_settings_streak_and_private_skin(tmp_path):
    import json, shutil
    from fastapi.testclient import TestClient
    from pathlib import Path
    from server.main import create_app
    home=tmp_path/"persisted"
    original=create_app(home,clock=lambda:NOW)
    secret=(home/"token.txt").read_text()
    pack=home/"packs"/"owner_skin"/"1.0.0"
    shutil.copytree(Path(__file__).resolve().parents[1]/"skins"/"study_companion",pack)
    skin_json=pack/"skin.json"
    manifest=json.loads(skin_json.read_text())
    manifest.update(id="owner_skin",name="Private owner skin")
    skin_json.write_text(json.dumps(manifest))
    with TestClient(original,headers={"Authorization":"Bearer "+secret}) as client:
        original.state.packs._cache=None
        settings=client.get("/v1/settings").json()
        settings.update(lesson_answers=31,skin_id="owner_skin",skin_version="1.0.0")
        assert client.put("/v1/settings",json=settings).status_code==200
        assert client.post("/v1/events",json={"events":[event()]}).status_code==200
        before=client.get("/v1/state").json()
    artwork_hash=__import__("hashlib").sha256(skin_json.read_bytes()).hexdigest()
    restarted=create_app(home,clock=lambda:NOW)
    assert (home/"token.txt").read_text()==secret
    with TestClient(restarted,headers={"Authorization":"Bearer "+secret}) as client:
        after=client.get("/v1/state").json()
        assert after["settings"]==before["settings"]
        assert after["progress"]==before["progress"]
        assert after["seed"]==before["seed"]
        assert after["streak"]==before["streak"]
        assert after["lineup"]==before["lineup"]
    assert __import__("hashlib").sha256(skin_json.read_bytes()).hexdigest()==artwork_hash

def test_authenticated_paginated_review_audit_retains_true_source_and_schema(client):
    items=[dict(event(i,1000,i+1),rating=4,interval=3,previous_interval=0)
           for i in range(4)]
    assert client.get('/v1/events/audit',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.post('/v1/events',json={'device_id':'phone','events':items}).json()['inserted']==4
    assert client.post('/v1/events',json={'device_id':'laptop','events':items}).json()['inserted']==0
    first=client.get('/v1/events/audit?limit=2').json()
    assert len(first['events'])==2 and first['next_cursor']
    assert first['events'][0]['schema_version']==1
    assert first['events'][0]['origin_device_id']=='phone'
    assert set(first['events'][0]['observed_on_devices'])=={'phone','laptop'}
    assert first['events'][0]['rating']==4 and first['events'][0]['interval']==3
    assert first['events'][0]['study_day']=='2026-10-29'
    second=client.get('/v1/events/audit',params={'after':first['next_cursor'],'limit':2}).json()
    assert len(second['events'])==2 and second['next_cursor'] is None
    ids=[row['id'] for row in first['events']+second['events']]
    assert ids==sorted(set(ids))
    assert client.get('/v1/events/audit?limit=10000').status_code==400


def test_large_review_history_pages_without_duplicate_answers(client):
    # Three thousand distinct Anki review IDs, deliberately retried by a
    # second device in descending order. Cursor pages must be stable.
    events=[event(i,2000,i+1) for i in range(3000)]
    for part in range(0,len(events),1000):
        assert client.post('/v1/events',json={
            'device_id':'phone','events':events[part:part+1000]}).json()['inserted']==1000
    for part in range(0,len(events),1000):
        assert client.post('/v1/events',json={
            'device_id':'laptop','events':list(reversed(events[part:part+1000]))}).json()['inserted']==0
    seen=set();cursor=''
    while True:
        result=client.get('/v1/events/audit',params={'after':cursor,'limit':500}).json()
        for row in result['events']:
            assert row['id'] not in seen
            seen.add(row['id'])
        if result['next_cursor'] is None:break
        assert result['next_cursor']>cursor
        cursor=result['next_cursor']
    assert len(seen)==3000
    assert client.get('/v1/state').json()['progress']['answers']==3000


def test_shared_revision_is_identical_on_two_devices_and_changes_only_with_confirmed_state(client):
    first=client.get('/v1/state?device_id=laptop').json()
    second=client.get('/v1/state?device_id=phone').json()
    assert first['shared_revision']==second['shared_revision']
    assert len(first['shared_revision'])==64
    assert client.post('/v1/events',json={'device_id':'phone','events':[event()]}).status_code==200
    changed=client.get('/v1/state?device_id=laptop').json()
    assert changed['shared_revision'] != first['shared_revision']
    assert changed['shared_revision']==client.get('/v1/state?device_id=phone').json()['shared_revision']
    assert client.post('/v1/events',json={'device_id':'phone','events':[event()]}).status_code==200
    assert changed['shared_revision']==client.get('/v1/state').json()['shared_revision']
    assert client.get('/v1/state').json()['progress']['answers']==1


def test_shared_revision_is_not_a_native_sync_receipt_or_wall_clock(tmp_path):
    from companion.consistency import shared_revision
    a={'date':'2026-11-02','settings':{},'policy':{},'lineup':{},'seed':'seed',
       'completed':False,'streak':0,'progress':{'answers':12},'today_events':[],
       'week':[], 'devices':[{'device_id':'phone'}], 'server_time_ms':20}
    b=dict(a,devices=[{'device_id':'laptop'}],server_time_ms=99999999)
    assert shared_revision(a)==shared_revision(b)
    b['progress']={'answers':13}
    assert shared_revision(a)!=shared_revision(b)


def test_update_restart_preserves_confirmed_history_settings_and_token(tmp_path):
    import hashlib
    from server.main import create_app
    data=tmp_path/'state'
    app=create_app(data,clock=lambda:NOW)
    token=(data/'token.txt').read_bytes()
    art=data/'packs'/'owner-private'/'1.0.0'/'original.png'
    art.parent.mkdir(parents=True);art.write_bytes(b'original private image content')
    with TestClient(app,headers={'Authorization':'Bearer '+token.decode().strip()}) as first:
        settings=first.get('/v1/settings').json()
        settings['lesson_answers']=77
        assert first.put('/v1/settings',json=settings).status_code==200
        assert first.post('/v1/events',json={'device_id':'phone','events':[event()]}).status_code==200
        before=first.get('/v1/state').json()
    saved_hash=hashlib.sha256(art.read_bytes()).hexdigest()
    later=create_app(data,clock=lambda:NOW)
    assert (data/'token.txt').read_bytes()==token
    with TestClient(later,headers={'Authorization':'Bearer '+token.decode().strip()}) as after:
        assert after.get('/v1/state').json()['shared_revision']==before['shared_revision']
        assert after.get('/v1/state').json()['progress']==before['progress']
        assert after.get('/v1/settings').json()['lesson_answers']==77
        assert after.get('/v1/events/audit').json()['events'][0]['origin_device_id']=='phone'
    assert hashlib.sha256(art.read_bytes()).hexdigest()==saved_hash


def test_existing_db_missing_pairing_token_fails_closed_without_replacing_state(tmp_path):
    from server.main import create_app
    data=tmp_path/'state'
    create_app(data)
    db=data/'companion.sqlite3';original=db.read_bytes()
    (data/'token.txt').unlink()
    with pytest.raises(RuntimeError,match='no pairing token'):
        create_app(data)
    assert not (data/'token.txt').exists()
    assert db.read_bytes()==original


def test_partial_or_corrupt_existing_db_is_never_silently_initialized(tmp_path):
    import sqlite3
    from server.store import Store
    path=tmp_path/'partial.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE owner_notes(note TEXT NOT NULL)')
        db.execute('INSERT INTO owner_notes VALUES (?)',('DO NOT ERASE',))
    with pytest.raises(RuntimeError,match='missing required tables'):
        Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT note FROM owner_notes').fetchone()[0]=='DO NOT ERASE'


def test_shared_revision_uses_stable_ordered_review_ids(client):
    reviews=[event(4,1000,5),event(1,1000,2),event(3,1000,4)]
    assert client.post('/v1/events',json={'device_id':'phone','events':reviews}).status_code==200
    a=client.get('/v1/state').json()
    ids=[e['id'] for e in a['today_events']]
    assert ids==sorted(ids)
    assert a['shared_revision']==client.get('/v1/state').json()['shared_revision']
