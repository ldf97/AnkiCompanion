"""#2/#6/#8/#9: every answer tracked and authenticated cross-device wakeups."""
import importlib.util
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

from fastapi.testclient import TestClient
from server.main import create_app

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'test-token-at-least-16-chars'
NOW = 1762012800000

# Load this dependency-free helper without importing Anki's GUI-only addon.
spec = importlib.util.spec_from_file_location('review_epoch', ROOT/'anki_addon/review_epoch.py')
epoch_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(epoch_module)
ReviewEpoch = epoch_module.ReviewEpoch


def review(n=1):
    return dict(collection_id='primary', revlog_id=NOW+n*1000,
                card_id=n, duration_ms=1000, rating=3)


def test_multiple_answers_during_inflight_sync_do_not_get_falsely_acked():
    generations=ReviewEpoch()
    assert generations.answer()==1
    assert generations.needs_scan and generations.needs_sync
    generations.scan_complete()
    generations.upload_complete(1)
    started=generations.sync_started()
    assert started==1
    # Two later answers happen while the first native Anki sync is running.
    assert generations.answer()==2
    assert generations.answer()==3
    assert generations.needs_scan
    assert not generations.sync_complete(started)
    assert generations.needs_sync and generations.synced==1
    generations.scan_complete()
    generations.upload_complete(3)
    assert generations.sync_complete(generations.sync_started())
    assert generations.synced==3
    assert not generations.needs_scan and not generations.needs_sync


def test_worker_cannot_ack_an_answer_posted_after_its_outbox_snapshot():
    generations=ReviewEpoch()
    for _ in range(6):generations.answer()
    batch=generations.scan_complete()
    generations.answer()
    generations.upload_complete(batch)
    assert generations.uploaded==6 and generations.answered==7
    assert generations.sync_started()==6
    assert not generations.sync_complete(6)
    generations.scan_complete()
    generations.upload_complete(7)
    assert generations.sync_complete(7)


def test_changes_long_poll_wakes_other_device_under_five_seconds(tmp_path):
    c=TestClient(create_app(tmp_path,TOKEN,lambda:NOW+100_000),
                 headers={'Authorization':'Bearer '+TOKEN})
    current=c.get('/v1/changes').json()['sequence']
    started=Event();received={}
    def watch():
        started.set()
        received['response']=c.get('/v1/changes',params={'since':current,'wait_ms':3500})
    thread=Thread(target=watch,daemon=True)
    start=monotonic();thread.start();assert started.wait(1)
    sleep(.05)
    assert c.post('/v1/events',json={'device_id':'phone','events':[review()]}).status_code==200
    thread.join(timeout=4)
    assert not thread.is_alive(), 'Server did not notify other device within 4s'
    data=received['response'].json()
    assert received['response'].status_code==200
    assert data['changed'] and data['sequence']>current and not data['reset']
    assert monotonic()-start<5
    # Retried identical answer cannot generate a second change notification.
    assert c.post('/v1/events',json={'device_id':'phone','events':[review()]}).json()['inserted']==0
    assert c.get('/v1/changes').json()['sequence']==data['sequence']
    # A completed native Anki upload signals a *new* scheduling revision.
    ticket=c.get('/v1/state?device_id=phone').json()['native_sync']['outgoing_ticket']
    assert ticket
    assert c.post('/v1/snapshots',json=dict(device_id='phone',label='Phone',decks=[],
             native_upload_ticket=ticket,sync_status='synced',
             collection_synced_ms=NOW+100_000)).status_code==200
    native=c.get('/v1/changes').json()['sequence']
    assert native==data['sequence']+1
    assert c.get('/v1/state?device_id=laptop').json()['native_sync']['pending']
    # The event feed survives a server process restart, unlike process memory.
    again=TestClient(create_app(tmp_path,TOKEN,lambda:NOW+100_000),
                     headers={'Authorization':'Bearer '+TOKEN})
    assert again.get('/v1/changes').json()['sequence']==native


def test_change_feed_auth_validation_timeout_and_command_wakeup(tmp_path):
    c=TestClient(create_app(tmp_path,TOKEN,lambda:NOW+100_000),
                 headers={'Authorization':'Bearer '+TOKEN})
    assert c.get('/v1/changes',headers={'Authorization':'Bearer invalid'}).status_code==401
    assert c.get('/v1/changes?since=-1').status_code==400
    assert c.get('/v1/changes?wait_ms=9000').status_code==400
    baseline=c.get('/v1/changes').json()['sequence']
    assert c.get('/v1/changes',params={'since':baseline,'wait_ms':25}).json()['changed'] is False
    assert c.get('/v1/changes',params={'since':baseline+999}).json()['reset'] is True
    assert c.post('/v1/commands',json={'device_id':'desktop','action':'study','deck_id':'123'}).status_code==200
    assert c.get('/v1/changes').json()['sequence']==baseline+1


def test_desktop_wakes_on_authenticated_change_and_tracks_each_hook():
    addon=(ROOT/'anki_addon/bridge.py').read_text()
    assert 'def watch_changes(self):' in addon
    assert "'/v1/changes?since='" in addon
    assert 'self.answers.answer()' in addon
    assert 'self.answers.sync_started()' in addon
    assert 'self.answers.sync_complete(started_epoch)' in addon


def test_repeated_undo_does_not_revoke_inflight_native_sync_ticket(tmp_path):
    c=TestClient(create_app(tmp_path,TOKEN,lambda:NOW+100_000),
                 headers={'Authorization':'Bearer '+TOKEN})
    c.post('/v1/events',json={'device_id':'phone','events':[review()]})
    identity=f"primary:{review()['revlog_id']}:{review()['card_id']}"
    assert c.post('/v1/events/retract',json={'device_id':'phone','ids':[identity]}).status_code==200
    first=c.get('/v1/state?device_id=phone').json()['native_sync']['outgoing_ticket']
    sequence=c.get('/v1/changes').json()['sequence']
    assert c.post('/v1/events/retract',json={'device_id':'phone','ids':[identity]}).status_code==200
    after=c.get('/v1/state?device_id=phone').json()['native_sync']['outgoing_ticket']
    assert first==after and c.get('/v1/changes').json()['sequence']==sequence
