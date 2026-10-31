"""Offline, deterministic release-feed regression tests."""
import hashlib, json
from io import BytesIO
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from server.main import create_app
from server.updates import ReleaseFeed, UpdateError

REPO='example/anki-companion'
PAYLOAD=b'fake installer content'
SHA=hashlib.sha256(PAYLOAD).hexdigest()
ASSET='AnkiCompanion-win.exe'

def fixture_feed(tmp_path, *, corrupt=False, bad_tag=False, wrong_size=False, missing_manifest=False):
    manifest={'schema_version':1,'version':'1.2.3','build':12,'commit':'a'*40,
              'assets':{'windows':{'filename':ASSET,'size':len(PAYLOAD)+(1 if wrong_size else 0),'sha256':('0'*64 if corrupt else SHA)}}}
    release={'tag_name':'v9.9.9' if bad_tag else 'v1.2.3','draft':False,'prerelease':False,
             'body':'Notes','html_url':'https://github.com/example/anki-companion/releases/tag/v1.2.3',
             'assets':[{'name':ASSET,'id':42,'size':len(PAYLOAD)},
                       *([] if missing_manifest else [{'name':'update.json','id':41,'size':100}])]}
    def fetch(url,accept='application/vnd.github+json'):
        if url.endswith('/releases/latest'):return json.dumps(release).encode()
        if url.endswith('/releases/assets/41'):return json.dumps(manifest).encode()
        raise AssertionError('Unexpected network request '+url)
    return ReleaseFeed(tmp_path,fetch=fetch)

def test_update_discovery_and_cache(tmp_path):
    feed=fixture_feed(tmp_path)
    assert feed.check(REPO,'windows','1.0.0')['available'] is True
    assert feed.check(REPO,'windows','1.2.3')['available'] is False
    assert feed.check(REPO,'android','1.0.0')['available'] is False
    assert feed.check('', 'windows','1.0.0')['configured'] is False
    assert feed.check(REPO,'windows','1.0.0')['download_path']=='/v1/updates/download/42'

def test_invalid_release_metadata(tmp_path):
    for kwargs in ({'bad_tag':True},{'wrong_size':True},{'missing_manifest':True}):
        with pytest.raises(UpdateError):fixture_feed(tmp_path,**kwargs).release(REPO)
    with pytest.raises(UpdateError):fixture_feed(tmp_path).release('bad repo')

def test_checksum_validation_and_no_partial_file(tmp_path):
    feed=fixture_feed(tmp_path);feed.release(REPO)
    class Response(BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    class Opener:
        def open(self,*args,**kwargs):return Response(PAYLOAD)
    with patch('server.updates.urllib.request.build_opener',return_value=Opener()):
        path,name=feed.download(REPO,'42')
    assert name==ASSET and path.read_bytes()==PAYLOAD
    assert not list(tmp_path.glob('*.partial'))
    bad=fixture_feed(tmp_path/'bad',corrupt=True);bad.release(REPO)
    with patch('server.updates.urllib.request.build_opener',return_value=Opener()):
        with pytest.raises(UpdateError,match='checksum'):bad.download(REPO,'42')
    assert not list((tmp_path/'bad').glob('*.partial'))

def test_update_endpoint_requires_auth(tmp_path,monkeypatch):
    monkeypatch.setenv('ANKI_COMPANION_REPOSITORY',REPO)
    app=create_app(tmp_path/'api','a-very-long-test-token')
    app.state.feed=fixture_feed(tmp_path/'feed')
    # Endpoints close over the original feed, so replace its fetch rather than its reference.
    original=app.state.feed
    app_feed=next(c.cell_contents for c in app.router.routes if getattr(c,'path',None)=='/v1/updates/{platform}' for c in (c.endpoint.__closure__ or []) if isinstance(c.cell_contents,ReleaseFeed))
    app_feed.fetch=original.fetch
    with TestClient(app) as client:
        assert client.get('/v1/updates/windows?current=1.0.0').status_code==401
        headers={'Authorization':'Bearer a-very-long-test-token'}
        assert client.get('/v1/updates/windows?current=1.0.0',headers=headers).json()['available'] is True
        assert client.get('/v1/updates/unknown',headers=headers).status_code==404


def test_windows_installer_publisher_is_pinned():
    from companion.updates import validate_windows_signature
    thumb='A'*40
    validate_windows_signature({'status':'Valid','thumbprint':thumb},thumb)
    for signature,pinned in [({'status':'NotSigned','thumbprint':thumb},thumb),({'status':'Valid','thumbprint':'B'*40},thumb),({'status':'Valid','thumbprint':thumb},'')]:
        with pytest.raises(ValueError):validate_windows_signature(signature,pinned)


def test_no_releases_is_not_a_connection_failure(tmp_path):
    from urllib.error import HTTPError
    def missing(*args):raise HTTPError('https://api.github.com/repos/example/repo/releases/latest',404,'Not found',{},None)
    result=ReleaseFeed(tmp_path,fetch=missing).check(REPO,'windows','0.1.1')
    assert result['configured'] and not result['available'] and 'approved' in result['message']


def test_official_github_windows_release_updates_without_paid_certificate(tmp_path, monkeypatch):
    """A hashed official GitHub installer is usable without Authenticode."""
    from companion import updates
    from unittest.mock import MagicMock
    payload=b'windows installer bytes'
    manifest={
        'schema_version':1,'version':'8.4.1','build':8401,'commit':'a'*40,
        'assets':{'windows':{'filename':'AnkiCompanion-Windows-Setup.exe',
                              'sha256':hashlib.sha256(payload).hexdigest(),'size':len(payload)}}
    }
    class Data(BytesIO):
        def geturl(self):return updates.PUBLIC_RELEASES+'update.json'
    monkeypatch.setattr(updates.urllib.request,'urlopen',lambda *a,**k:Data(json.dumps(manifest).encode()))
    result=updates.github_release('windows')
    assert result['available'] and result['download_url'].startswith(updates.PUBLIC_RELEASES)
    installer=tmp_path/result['filename'];installer.write_bytes(payload)
    monkeypatch.setattr(updates.sys,'platform','win32')
    monkeypatch.setattr(updates,'version',lambda:{'version':'0.1.1','windows_signer_thumbprint':''})
    launched=[]
    monkeypatch.setattr(updates.subprocess,'Popen',lambda args,**kwargs:launched.append(args))
    updates.install(installer,result)
    assert launched and launched[0][0]==str(installer)
    installer.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='checksum'):updates.install(installer,result)


def test_github_unsigned_release_cannot_launch_arbitrary_executable(tmp_path,monkeypatch):
    from companion import updates
    executable=tmp_path/'some-installer.exe';executable.write_bytes(b'x')
    monkeypatch.setattr(updates.sys,'platform','win32')
    with pytest.raises(ValueError,match='official'):updates.install(executable,None)
