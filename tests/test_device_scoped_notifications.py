"""Requirements 2, 6, 8, 9, 10: real multi-client HTTP and durable cursors."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep
from zipfile import ZipFile
import sqlite3

from fastapi.testclient import TestClient
from server.main import create_app

NOW=1762012800000
TOKEN='server-change-notifications-test-token'


def client(root):
    return TestClient(create_app(root,TOKEN,lambda:NOW+200000),
                      headers={'Authorization':'Bearer '+TOKEN})


def event(n=1,collection='primary'):
    return dict(collection_id=collection, revlog_id=NOW+n*1000,card_id=n,
                rating=3,duration_ms=1500,interval=3,previous_interval=1)


def changes(c,device='',collection='primary',since=0,wait=0):
    return c.get('/v1/changes',params=dict(since=since,wait_ms=wait,
                    device_id=device,collection_id=collection)).json()


def test_review_ack_without_origin_echo_and_remote_notification(tmp_path):
    c=client(tmp_path)
    baseline=changes(c)['sequence']
    r=c.post('/v1/events',json={'device_id':'pc1','events':[event()]})
    assert r.status_code==200 and r.json()['inserted']==1
    original=changes(c,'pc1',since=baseline)
    remote=changes(c,'phone',since=baseline)
    assert original['changed'] is False and original['reset'] is False
    assert original['sequence']>baseline
    assert remote['changed'] is True and remote['sequence']==original['sequence']
    assert changes(c,'pc2',collection='other',since=baseline)['changed'] is False
    assert c.post('/v1/events',json={'device_id':'pc1','events':[event()]}).json()['inserted']==0
    assert changes(c)['sequence']==original['sequence']
    # A review can't be echoed back to its uploader merely because a second
    # device reports that same ID while reconciling native history.
    assert c.post('/v1/events',json={'device_id':'phone','events':[event()]}).json()['inserted']==0
    assert changes(c)['sequence']==original['sequence']


def test_native_receipt_wakes_only_other_devices_and_keeps_collection_scope(tmp_path):
    c=client(tmp_path)
    r=c.post('/v1/events',json={'device_id':'phone','events':[event()]}).json()
    cursor=changes(c)['sequence']
    ticket=r['native_upload_tickets']['primary']
    assert c.post('/v1/snapshots',json=dict(device_id='phone',label='Phone',decks=[],
                        sync_status='synced',collection_synced_ms=NOW+5000,
                        native_upload_ticket=ticket)).status_code==200
    assert changes(c,'phone',since=cursor)['changed'] is False
    assert changes(c,'pc1',since=cursor)['changed'] is True
    assert changes(c,'pc1','other',since=cursor)['changed'] is False
    assert c.get('/v1/state?device_id=pc1').json()['native_sync']['pending']
    assert not c.get('/v1/state?device_id=phone').json()['native_sync']['pending']


def test_two_collections_and_batched_reviews_route_independently(tmp_path):
    c=client(tmp_path)
    start=changes(c)['sequence']
    response=c.post('/v1/events',json={'device_id':'phone','events':[event(1),event(2,'secondary')]})
    assert response.status_code==200 and response.json()['inserted']==2
    assert changes(c,'laptop','primary',start)['changed']
    assert changes(c,'laptop','secondary',start)['changed']
    assert changes(c,'phone','primary',start)['changed'] is False
    assert changes(c,'laptop','unrelated',start)['changed'] is False


def test_command_is_targeted_to_one_device_and_settings_are_broadcast(tmp_path):
    c=client(tmp_path)
    before=changes(c)['sequence']
    assert c.post('/v1/commands',json=dict(device_id='laptop',action='sync',deck_id='')).status_code==200
    assert changes(c,'laptop',since=before)['changed'] is True
    assert changes(c,'phone',since=before)['changed'] is False
    after=changes(c)['sequence']
    settings=c.get('/v1/settings').json()
    settings['lesson_answers']+=1
    assert c.put('/v1/settings',json=settings).status_code==200
    assert changes(c,'phone',since=after)['changed'] is True
    assert changes(c,'laptop',since=after)['changed'] is True


def test_device_specific_long_poll_under_five_seconds(tmp_path):
    phone=client(tmp_path)
    laptop=client(tmp_path)
    cursor=changes(laptop)['sequence']
    start=monotonic()
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending=executor.submit(changes,laptop,'laptop','primary',cursor,3500)
        sleep(.12)
        assert phone.post('/v1/events',json={'device_id':'phone','events':[event()]}).status_code==200
        response=pending.result(timeout=4.0)
    assert response['changed'] and response['sequence']>cursor
    assert monotonic()-start<5
    assert changes(phone,'phone',since=cursor)['changed'] is False


def test_reconnect_from_old_cursor_and_nonblocking_filter(tmp_path):
    c=client(tmp_path)
    before=changes(c)['sequence']
    for i in range(5):
        c.post('/v1/events',json={'device_id':'phone','events':[event(i+1)]})
    again=client(tmp_path)
    assert changes(again,'laptop',since=before)['changed'] is True
    assert changes(again,'phone',since=before)['changed'] is False
    after=changes(again)['sequence']
    assert changes(again,'laptop',since=after,wait=20)['changed'] is False
    assert changes(again,'laptop',since=after+1000)['reset'] is True
    assert again.get('/v1/changes?collection_id=../bad').status_code==400
    assert again.get('/v1/changes?device_id='+('x'*101)).status_code==400
    assert again.get('/v1/changes',headers={'Authorization':'Bearer wrong'}).status_code==401
    # All changes have an atomic log entry, without review text/credentials.
    with sqlite3.connect(tmp_path/'companion.sqlite3') as db:
        raw=db.execute('SELECT seq,collection,origin_device,target_device,kind FROM change_events ORDER BY seq').fetchall()
    assert len(raw)==5 and all(x[1:] == ('primary','phone','','review') for x in raw)


def test_windows_addon_archive_acceptance_covers_review_epoch_dependency(tmp_path,monkeypatch):
    from desktop import bootstrap
    from subprocess import run
    from sys import executable
    root=Path(__file__).resolve().parents[1]
    run([executable,str(root/'scripts/package_addon.py')],cwd=root,check=True)
    package=root/'packages/Anki_Companion_Bridge.ankiaddon'
    with ZipFile(package) as z:
        assert set(z.namelist()) == bootstrap.ADDON_SOURCE_FILES
        assert 'review_epoch.py' in z.namelist()
    roaming=tmp_path/'Roaming';(roaming/'Anki2').mkdir(parents=True)
    monkeypatch.setenv('APPDATA',str(roaming))
    monkeypatch.setattr(bootstrap,'addon_archive',lambda:package)
    assert 'installed' in bootstrap.ensure_anki_bridge()
    installed=roaming/'Anki2/addons21/anki_companion_bridge'
    assert (installed/'bridge.py').is_file() and (installed/'review_epoch.py').is_file()


def test_addon_observes_review_hooks_and_avoids_premature_upload_ack():
    root=Path(__file__).resolve().parents[1]
    bridge=(root/'anki_addon/bridge.py').read_text()
    hooks=(root/'anki_addon/__init__.py').read_text()
    assert "('reviewer_did_answer_card', _answer)" in hooks
    assert 'self.answers.answer()' in bridge
    assert "if not has_unsent and not has_undos:" in bridge
    assert 'uploaded_generation=captured_generation' in bridge
    assert "'/v1/changes?since='" in bridge
    assert "'&device_id='+quote(" in bridge
    assert "state.get('changed',False)" in bridge
