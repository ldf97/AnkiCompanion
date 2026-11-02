"""A native undo reverses scheduling, never a real day's study accountability."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from server.main import create_app

TOKEN='undo-accountability-integration-token'
NOW=int(datetime(2026,10,29,16,tzinfo=timezone.utc).timestamp()*1000)


def client(root,now=NOW):
    return TestClient(create_app(root,TOKEN,lambda:now),
                      headers={'Authorization':'Bearer '+TOKEN})


def review(n,day_shift=0):
    return dict(collection_id='primary',card_id=n,revlog_id=NOW-60_000+n-day_shift*86_400_000,
                rating=3,duration_ms=30_000)


def key(item):
    return f"{item['collection_id']}:{item['revlog_id']}:{item['card_id']}"


def test_undo_synchronizes_native_change_but_keeps_daily_streak(tmp_path):
    c=client(tmp_path)
    initial=c.get('/v1/settings').json()
    initial.update(lesson_answers=2,lesson_ms=60_000)
    assert c.put('/v1/settings',json=initial).status_code==200
    items=[review(1),review(2)]
    posted=c.post('/v1/events',json={'device_id':'pc1','events':items}).json()
    assert posted['inserted']==2
    ticket=posted['native_upload_tickets']['primary']
    assert c.post('/v1/snapshots',json=dict(device_id='pc1',collection_id='primary',
        label='PC1',decks=[],native_upload_ticket=ticket, sync_status='synced',
        collection_synced_ms=NOW+1000)).status_code==200
    before=c.get('/v1/state?device_id=phone').json()
    assert before['streak']==1 and before['completed']
    assert before['progress']['answers']==2
    assert before['native_sync']['pending']
    cursor=c.get('/v1/changes').json()['sequence']

    # Native undo on PC1: the server tells phone/PC2 to refresh scheduling.
    r=c.post('/v1/events/retract',json={'device_id':'pc1','ids':[key(items[0])]})
    assert r.status_code==200
    assert not c.get('/v1/changes',params=dict(since=cursor,device_id='pc1',collection_id='primary')).json()['changed']
    for other in ('phone','pc2'):
        assert c.get('/v1/changes',params=dict(since=cursor,device_id=other,collection_id='primary')).json()['changed']
    after=c.get('/v1/state?device_id=phone').json()
    assert after['completed'] and after['streak']==1
    assert after['progress']['answers']==2 and after['progress']['duration_ms']==60_000
    assert after['progress']['active_reviews']==1
    assert after['native_sync']['pending']
    assert {x['id']:x['retracted'] for x in c.get('/v1/events/audit').json()['events']}[key(items[0])]

    # Upload undo to AnkiWeb and confirm a fresh native receipt. Replaying
    # the same undo must not add another activity unit or wake all devices.
    outgoing=c.get('/v1/state?device_id=pc1').json()['native_sync']['outgoing_ticket']
    assert outgoing and outgoing!=ticket
    assert c.post('/v1/snapshots',json=dict(device_id='pc1',label='PC1',decks=[],
                     collection_id='primary',native_upload_ticket=outgoing,
                     collection_synced_ms=NOW+2000,sync_status='synced')).status_code==200
    revised=c.get('/v1/state?device_id=phone').json()['native_sync']['revision']
    assert revised>=2
    current=c.get('/v1/changes').json()['sequence']
    assert c.post('/v1/events/retract',json={'device_id':'pc1','ids':[key(items[0])]}).status_code==200
    assert c.get('/v1/changes').json()['sequence']==current
    assert c.get('/v1/state').json()['streak']==1


def test_out_of_order_undo_and_offline_retry_preserve_accountability(tmp_path):
    c=client(tmp_path)
    items=[review(n) for n in range(1,11)]
    key1=key(items[0])
    # Device sends its undo before a disconnected outbox uploads the answer.
    assert c.post('/v1/events/retract',json={'device_id':'phone','ids':[key1]}).status_code==200
    c.post('/v1/events',json={'device_id':'phone','events':items})
    assert c.get('/v1/state').json()['completed']
    assert c.get('/v1/state').json()['streak']==1
    assert c.get('/v1/state').json()['progress']['active_reviews']==9
    # A second device replays all native rows after reconnect: no duplicates.
    assert c.post('/v1/events',json={'device_id':'pc2','events':items}).json()['inserted']==0
    restarted=client(tmp_path)
    s=restarted.get('/v1/state').json()
    assert s['completed'] and s['streak']==1 and s['progress']['answers']==10
    assert s['progress']['active_reviews']==9


def test_undo_does_not_destroy_previous_day_streak(tmp_path):
    c=client(tmp_path)
    yesterday=[review(n,1) for n in range(1,11)]
    today=[review(n) for n in range(1,11)]
    c.post('/v1/events',json={'device_id':'pc1','events':yesterday+today})
    assert c.get('/v1/state').json()['streak']==2
    assert c.post('/v1/events/retract',json={'device_id':'phone','ids':
        [key(item) for item in yesterday]}).status_code==200
    state=c.get('/v1/state').json()
    assert state['streak']==2
    assert state['week'][-2]['completed'] is True
    assert state['week'][-1]['completed'] is True


def test_real_native_undo_hook_and_android_undo_path_are_wired():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    hooks=(root/'anki_addon/__init__.py').read_text()
    bridge=(root/'anki_addon/bridge.py').read_text()
    android=(root/'ankidroid_bridge/apply.py').read_text()
    overlay=(root/'android/app/src/main/java/org/ankicompanion/app/Outbox.kt').read_text()
    assert "('state_did_undo', _undo)" in hooks
    assert 'self.undo_requested=True' in bridge
    assert 'latest_undos>prior_undos' in bridge
    assert 'self.answers.answer()' in bridge
    assert 'CompanionIntegration.requestSync()' in android
    assert 'UPDATE events SET undone=1' in overlay
    assert 'merged[c.getString(0)]=item.getLong("duration_ms")' in overlay


def test_offline_android_study_stays_available():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    sync=(root/'android/app/src/main/java/org/ankicompanion/app/Sync.kt').read_text()
    main=(root/'android/app/src/main/java/org/ankicompanion/app/MainActivity.kt').read_text()
    assert 'fun prepareStudy(context:Context):JSONObject' in sync
    assert 'if(!available)return offlineStudy(context,store)' in sync
    assert 'if(store.getSetting("sync_error").isNotBlank())return offlineStudy(context,store)' in sync
    assert 'study_handoff_mode","offline"' in sync
    assert 'AnkiBridge.open(this,deck.getString("id"))' in main
