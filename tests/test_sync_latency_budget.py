"""Loopback <5s coordination budget. NOT a physical mobile/WAN latency claim."""
import time
from fastapi.testclient import TestClient
from server.main import create_app

NOW=1762012800000
TOKEN='test-token-at-least-16-chars'

def test_25_phone_reviews_dispatch_to_laptop_within_local_five_second_budget(tmp_path):
    c=TestClient(create_app(tmp_path,TOKEN,lambda:NOW+300_000),headers={'Authorization':'Bearer '+TOKEN})
    reviews=[dict(collection_id='primary',revlog_id=NOW+i*1000,card_id=i+1,
                  duration_ms=5000,rating=3) for i in range(25)]
    start=time.monotonic()
    receipt=c.post('/v1/events',json={'device_id':'phone','events':reviews})
    assert receipt.status_code==200 and receipt.json()['inserted']==25
    token=receipt.json()['native_upload_tickets']['primary']
    snap=dict(device_id='phone',label='phone',decks=[],sync_status='synced',
              collection_synced_ms=NOW+30_000,native_upload_ticket=token)
    assert c.post('/v1/snapshots',json=snap).status_code==200
    pending=c.get('/v1/state?device_id=laptop').json()['native_sync']
    assert pending['pending'] and pending['revision']==1
    assert time.monotonic()-start < 5.0
    # This asserts server dispatch only, not AnkiWeb or network sync latency.

def test_active_phone_background_poll_targets_one_second():
    from pathlib import Path
    src=(Path(__file__).resolve().parents[1]/"android/app/src/main/java/org/ankicompanion/app/LiveSyncService.kt").read_text()
    assert "postDelayed(this,1000)" in src
