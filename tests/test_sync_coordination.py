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

def snapshot(dev, synced=0, applied=0, status='synced', collection='primary',ticket=''):
    return dict(device_id=dev,label=dev,collection_id=collection,decks=[],
                sync_status=status,collection_synced_ms=synced,applied_revision=applied,
                native_upload_ticket=ticket)

def publish(c,device,synced,collection='primary'):
    ticket=c.get('/v1/state',params={'device_id':device,'collection_id':collection}).json()['native_sync']['outgoing_ticket']
    assert len(ticket)==32
    return c.post('/v1/snapshots',json=snapshot(device,synced=synced,collection=collection,ticket=ticket))

def check(c,dev):return c.get('/v1/state',params={'device_id':dev}).json()['native_sync']

def test_five_second_handoff_is_event_driven_not_a_deck_close(tmp_path):
    c=client(tmp_path)
    review=event()
    assert c.post('/v1/events',json={'device_id':'phone','events':[review]}).json()['inserted']==1
    # Local review has not yet reached Anki's native collection service.
    assert not check(c,'desktop')['pending']
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=0,status='syncing')).status_code==200
    assert not check(c,'desktop')['pending']
    assert publish(c,'phone',T+1500).status_code==200
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
    assert publish(c,'phone',T+3500).status_code==200
    assert check(c,'desktop')['revision']==1
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=T+3500)).status_code==200
    assert check(c,'desktop')['revision']==1
    assert c.post('/v1/events',json={'device_id':'phone','events':original}).json()['inserted']==0
    assert check(c,'desktop')['revision']==1

def test_offline_device_and_durable_receipts_survive_restart(tmp_path):
    first=client(tmp_path)
    first.post('/v1/events',json={'device_id':'phone','events':[event()]})
    publish(first,'phone',T+2500)
    assert check(first,'offline-PC')['pending']
    second=client(tmp_path)
    assert check(second,'offline-PC')['pending']
    second.post('/v1/snapshots',json=snapshot('offline-PC',synced=T+5000,applied=1))
    assert not check(second,'offline-PC')['pending']
    assert check(second,'phone')['revision']==1

def test_sync_ticket_rejects_stale_sync_and_wrong_device_ticket(tmp_path):
    c=client(tmp_path)
    receipt=c.post('/v1/events',json={'device_id':'phone','events':[event()]}).json()
    token=receipt['native_upload_tickets']['primary']
    # Android sync can have completed BEFORE the review was submitted to the
    # companion server. A newer wall clock alone proves absolutely nothing.
    c.post('/v1/snapshots',json=snapshot('phone',synced=T+999999))
    assert check(c,'desktop')['revision']==0
    c.post('/v1/snapshots',json=snapshot('desktop',synced=T+999999,ticket=token))
    assert check(c,'desktop')['revision']==0
    c.post('/v1/snapshots',json=snapshot('phone',synced=T+999999,ticket='a'*32))
    assert check(c,'desktop')['revision']==0
    assert c.post('/v1/snapshots',json=snapshot('phone',synced=T+999999,ticket=token)).status_code==200
    assert check(c,'desktop')['revision']==1
    assert not check(c,'phone')['outgoing_ticket']


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
    publish(c,'phone',T+2000,collection='secondary')
    assert check(c,'pc')['revision']==0
    assert c.get('/v1/state',params={'device_id':'pc','collection_id':'secondary'}).json()['native_sync']['pending']


def test_device_list_explicitly_exposes_stale_anime_review_collections(tmp_path):
    c=client(tmp_path)
    c.post('/v1/snapshots',json=snapshot('desktop',status='offline'))
    c.post('/v1/events',json={'device_id':'phone','events':[event()]})
    publish(c,'phone',T+2000)
    devices={d['device_id']:d for d in c.get('/v1/state').json()['devices']}
    assert devices['desktop']['native_sync']['pending']
    assert not devices['phone']['native_sync']['pending']

def test_sync_status_ui_distinguishes_server_progress_from_native_receipt():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    desktop=(root/"desktop/app.py").read_text()
    android=(root/"android/app/src/main/java/org/ankicompanion/app/MainActivity.kt").read_text()
    status=(root/"companion/status.py").read_text()
    assert "Anki sync pending {applied}/{latest}" in status
    assert "Anki sync confirmed {applied}/{latest}" in status
    assert "Anki sync not yet verified" in status
    assert 'device_status(device)' in desktop
    assert "Anki sync pending $applied/$revision" in android
    assert "Anki sync confirmed $applied/$revision" in android
    assert "Scheduling sync pending:" in android

def test_cross_device_test_holds_native_provider_alive_until_companion_finishes():
    """Avoid false instrument crash when Android kills a dependent process."""
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    phone=(root/"ankidroid_bridge/CompanionAcceptanceTest.kt").read_text()
    observer=(root/"android/app/src/androidTest/java/org/ankicompanion/app/CrossDeviceTest.kt").read_text()
    backend=(root/"scripts/emulator_backend.py").read_text()
    assert 'optBoolean("observer_finished")' in phone
    assert 'signal("observer-finished")' in observer
    assert "'observer-finished':'observer_finished'" in backend
    assert phone.index('assertTrue(control("/test/verify-phone"') < phone.index('optBoolean("observer_finished")')
    assert observer.index("widgetHost.stopListening()") < observer.index('signal("observer-finished")')


def test_device_liveness_and_native_receipts_are_separate(tmp_path):
    c=client(tmp_path)
    now=T+100_000
    c.post('/v1/snapshots',json=snapshot('laptop',synced=T+2000,status='synced'))
    first={d['device_id']:d for d in c.get('/v1/state').json()['devices']}
    assert first['laptop']['online'] is True
    assert first['laptop']['age_seconds']==0
    assert 'Anki sync not yet verified' in __import__('companion.status',fromlist=['device_status']).device_status(first['laptop'])
    # The server's clock is a deterministic fixture; test liveness at the
    # store layer to avoid silently trusting the Android wall clock.
    app=create_app(tmp_path,TOKEN,lambda:now+121_000)
    with TestClient(app,headers={'Authorization':'Bearer '+TOKEN}) as later:
        device=later.get('/v1/state').json()['devices'][0]
        assert device['online'] is False and device['age_seconds']==121
        assert 'offline (last seen 121s ago)' in __import__('companion.status',fromlist=['device_status']).device_status(device)


def test_device_receipt_does_not_imply_online(tmp_path):
    c=client(tmp_path)
    c.post('/v1/events',json={'device_id':'phone','events':[event()]})
    publish(c,'phone',T+2500)
    c.post('/v1/snapshots',json=snapshot('pc',synced=T+3500,applied=1))
    app=create_app(tmp_path,TOKEN,lambda:T+221_001)
    with TestClient(app,headers={'Authorization':'Bearer '+TOKEN}) as later:
        pc=next(d for d in later.get('/v1/state').json()['devices'] if d['device_id']=='pc')
        from companion.status import device_status
        assert pc['native_sync']['pending'] is False
        assert pc['online'] is False
        assert 'offline' in device_status(pc)
        assert 'Anki sync confirmed 1/1' in device_status(pc)


def test_status_ui_contains_confirmed_and_provisional_states():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    android=(root/'android/app/src/main/java/org/ankicompanion/app/MainActivity.kt').read_text()
    windows=(root/'desktop/app.py').read_text()
    assert 'provisional answer(s)' in android
    assert 'Anki sync confirmed $applied/$revision' in android
    assert 'last seen ${age}s ago' in android
    assert 'device_status(device)' in windows
    assert 'connection retry pending (using cached progress)' in windows