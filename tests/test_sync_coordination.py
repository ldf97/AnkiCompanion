"""Native Anki revisions track completed uploads, not guessed UI counter progress."""
from fastapi.testclient import TestClient
from server.main import create_app

T=1762012800000
TOKEN="test-token-at-least-16-chars"

def client(tmp_path):
    return TestClient(create_app(tmp_path,TOKEN,lambda:T+100_000),
                      headers={'Authorization':'Bearer '+TOKEN})

def event(i=1,rating=3):
    return dict(collection_id='primary',revlog_id=T+i*1000,card_id=i,
                duration_ms=8000,rating=rating,interval=4,previous_interval=1)

def snapshot(dev, synced=0, applied=0, status='synced', collection='primary'):
    return dict(device_id=dev,label=dev,collection_id=collection,decks=[],
                sync_status=status,collection_synced_ms=synced,applied_revision=applied)

def check(c,dev):return c.get('/v1/state',params={'device_id':dev}).json()['native_sync']

def test_five_second_handoff_is_event_driven_not_a_deck_close(tmp_path):
    c=client(tmp_path)
    review=event()
    assert c.post('/v1/events',json={'device_id':'phone','events':[review]}).json()['inserted']==1
    # Local review has not yet reached Anki's native collection service.
    assert not check(c,'desktop')['pending']
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=0,status='syncing')).status_code==200
    assert not check(c,'desktop')['pending']
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=T+1500)).status_code==200
    assert check(c,'desktop')['revision']==1 and check(c,'desktop')['pending']
    assert not check(c,'phone')['pending']
    assert c.post('/v1/snapshots',json=snapshot('pc1',synced=T+2500,applied=1)).status_code==200
    assert not check(c,'pc1')['pending']
    assert check(c,'pc2')['pending']

def test_multiple_answers_single_native_upload_and_no_duplicate_revisions(tmp_path):
    c=client(tmp_path)
    original=[event(1),event(2),event(3)]
    assert c.post('/v1/events',json={'device_id':'phone','events':original}).json()['inserted']==3
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=T+2500)).status_code==200
    assert not check(c,'desktop')['pending']  # third review not yet uploaded
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=T+3500)).status_code==200
    assert check(c,'desktop')['revision']==1
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=T+3500)).status_code==200
    assert check(c,'desktop')['revision']==1
    assert c.post('/v1/events',json={'device_id':'phone','events':original}).json()['inserted']==0
    assert check(c,'desktop')['revision']==1

def test_offline_device_and_durable_receipts_survive_restart(tmp_path):
    first=client(tmp_path)
    first.post('/v1/events',json={'device_id':'phone','events':[event()]})
    first.post('/v1/snapshots',json=snapshot('phone',synced=T+2500))
    assert check(first,'offline-PC')['pending']
    second=client(tmp_path)
    assert check(second,'offline-PC')['pending']
    second.post('/v1/snapshots',json=snapshot('offline-PC',synced=T+5000,applied=1))
    assert not check(second,'offline-PC')['pending']
    assert check(second,'phone')['revision']==1

def test_rating_enrichment_never_counts_twice(tmp_path):
    c=client(tmp_path)
    old={k:v for k,v in event().items() if k not in ('rating','interval','previous_interval')}
    assert c.post('/v1/events',json={'device_id':'phone','events':[old]}).status_code==200
    assert c.post('/v1/events',json={'device_id':'desktop','events':[event()]}).json()['inserted']==0
    assert c.post('/v1/events',json={'events':[event(rating=4)]}).status_code==409
    assert c.get('/v1/state').json()['progress']['answers']==1

def test_distinct_collections_do_not_sync_one_another(tmp_path):
    c=client(tmp_path)
    review={**event(),'collection_id':'secondary'}
    c.post('/v1/events',json={'device_id':'phone','events':[review]})
    c.post('/v1/snapshots',json=snapshot('phone',synced=T+2000,collection='secondary'))
    assert check(c,'pc')['revision']==0
    assert c.get('/v1/state',params={'device_id':'pc','collection_id':'secondary'}).json()['native_sync']['pending']


def test_device_list_explicitly_exposes_stale_anime_review_collections(tmp_path):
    c=client(tmp_path)
    c.post('/v1/snapshots',json=snapshot('desktop',status='offline'))
    c.post('/v1/events',json={'device_id':'phone','events':[event()]})
    c.post('/v1/snapshots',json=snapshot('phone',synced=T+2000))
    devices={d['device_id']:d for d in c.get('/v1/state').json()['devices']}
    assert devices['desktop']['native_sync']['pending']
    assert not devices['phone']['native_sync']['pending']
