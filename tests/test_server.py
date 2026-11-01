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

def test_review_rating_persists_and_old_client_can_enrich_without_double_count(client):
    review = event()
    old = client.post('/v1/events', json={'device_id':'old-phone', 'events':[review]})
    assert old.status_code == 200 and old.json()['inserted'] == 1
    newer = dict(review, rating=3)
    updated = client.post('/v1/events', json={'device_id':'desktop', 'events':[newer]})
    assert updated.status_code == 200 and updated.json()['inserted'] == 0
    stored = client.app.state.store
    with stored.tx() as db:
        row = db.execute('SELECT payload FROM events WHERE id=?',
                         (f"primary:{review['revlog_id']}:{review['card_id']}",)).fetchone()
        assert json.loads(row['payload'])['rating'] == 3
    assert client.get('/v1/state').json()['progress']['answers'] == 1
    assert client.post('/v1/events', json={'events':[dict(newer, rating=4)]}).status_code == 409


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
    assert client.get('/v1/state').json()['progress']['answers']==0

def test_undo_recomputes_completion(client):
    items=[event(i,card=i+1) for i in range(10)]
    client.post('/v1/events',json={'events':items})
    client.post('/v1/events/retract',json={'ids':[f"primary:{items[0]['revlog_id']}:1"]})
    assert not client.get('/v1/state').json()['completed']

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
