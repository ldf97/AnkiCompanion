"""A real Anki native revlog uses integer timestamp IDs, not card compound IDs.

Two offline replicas can independently create an identical ID for different
cards. Companion must retain both accountability events but must never falsely
certify that two distinct rows with one PRIMARY KEY both reached AnkiWeb.
"""
from fastapi.testclient import TestClient
from server.main import create_app
from companion.status import device_status

TOKEN='test-native-id-collision-gym-token'
NOW=1762012800000


def make(tmp_path):
    return TestClient(create_app(tmp_path,TOKEN,lambda:NOW+100_000),
                      headers={'Authorization':'Bearer '+TOKEN})


def review(card,revlog=NOW+5_000,collection='primary'):
    return dict(collection_id=collection,revlog_id=revlog,card_id=card,
                duration_ms=10_000,rating=3,interval=4,previous_interval=0)


def test_two_offline_devices_same_native_revlog_id_are_not_silently_merged(tmp_path):
    client=make(tmp_path)
    a=client.post('/v1/events',json={'device_id':'phone','events':[review(10)]})
    assert a.status_code==200 and a.json()['inserted']==1
    first=a.json()['native_upload_tickets']['primary']
    b=client.post('/v1/events',json={'device_id':'pc2','events':[review(11)]})
    assert b.status_code==200 and b.json()['inserted']==1
    native=client.get('/v1/state',params={'device_id':'phone'}).json()['native_sync']
    assert native['conflicted'] and native['native_collision_count']==1
    assert client.get('/v1/state').json()['progress']['answers']==2
    assert client.get('/v1/state').json()['progress']['active_reviews']==2
    # Even if the phone claims it synced, native Anki has one primary-key slot
    # for these two review attempts; never issue false scheduling receipt.
    for who,ticket in (('phone',first),('pc2',b.json()['native_upload_tickets']['primary'])):
        result=client.post('/v1/snapshots',json=dict(device_id=who,label=who,
            collection_id='primary',decks=[],sync_status='synced',
            native_upload_ticket=ticket,collection_synced_ms=NOW+100_000))
        assert result.status_code==200
        status=client.get('/v1/state',params={'device_id':who}).json()['native_sync']
        assert status['revision']==0 and status['outgoing_ticket']==ticket
    entries=client.get('/v1/events/audit').json()['events']
    assert {e['card_id'] for e in entries}=={10,11}
    assert len(entries)==2
    assert 'collision' in device_status(client.get('/v1/state').json()['devices'][0]).lower()
    # Replayed packets must not rotate the collision ticket or double-count.
    assert client.post('/v1/events',json={'device_id':'pc2','events':[review(11)]}).json()['inserted']==0
    assert client.get('/v1/state').json()['progress']['answers']==2
    restarted=make(tmp_path)
    assert restarted.get('/v1/state',params={'device_id':'phone'}).json()['native_sync']['conflicted']


def test_distinct_collections_and_distinct_review_ids_do_not_raise_false_conflict(tmp_path):
    c=make(tmp_path)
    for who,events in [('pc1',[review(1)]),('phone',[review(2,NOW+5001)]),
                       ('different-profile',[review(3,collection='second')])]:
        assert c.post('/v1/events',json={'device_id':who,'events':events}).status_code==200
    for col in ('primary','second'):
        assert not c.get('/v1/state',params={'device_id':'pc2','collection_id':col}).json()['native_sync']['conflicted']


def test_collision_guard_is_exercised_by_both_platform_study_entrypoints():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    android=(root/'android/app/src/main/java/org/ankicompanion/app/Sync.kt').read_text()
    desktop=(root/'anki_addon/bridge.py').read_text()
    assert 'if(nativeCollision)' in android
    assert 'if(before.getJSONObject("native_sync").optBoolean("conflicted"))' in android
    assert 'self.native_collision_blocked=bool(native.get' in desktop
    assert 'self.syncing or self.native_collision_blocked' in desktop
