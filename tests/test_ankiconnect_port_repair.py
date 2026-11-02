"""Regression: Companion must coexist with AnkiConnect, not commandeer 8765."""
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from companion.ports import LOCAL_URL, migrate_local_url
from desktop import bootstrap


@pytest.mark.parametrize('url', [
    'http://127.0.0.1:8765', 'http://127.0.0.1:8765/',
    'http://localhost:8765', 'http://[::1]:8765',
])
def test_legacy_loopback_companion_endpoints_only(url):
    assert migrate_local_url(url) == 'http://127.0.0.1:8766'


@pytest.mark.parametrize('url', [
    'https://host.example.com', 'http://192.168.1.8:8765',
    'https://127.0.0.1:8765', 'http://127.0.0.1:8765/admin',
    'http://127.0.0.1:8766', 'https://host.example.com:8765',
])
def test_remote_and_new_urls_never_rewritten(url):
    assert migrate_local_url(url) == url


def packaged_addon(tmp_path):
    archive=tmp_path/'bridge.ankiaddon'
    source=Path(__file__).resolve().parents[1]/'anki_addon'
    with ZipFile(archive,'w') as z:
        for name in sorted(bootstrap.ADDON_SOURCE_FILES):
            z.write(source/name,arcname=name)
    return archive


def test_repair_keeps_addon_preferences_and_migrates_meta_without_duplicates(tmp_path,monkeypatch):
    roaming=tmp_path/'Roaming'
    path=roaming/'Anki2'/'addons21'/'anki_companion_bridge'
    path.mkdir(parents=True)
    token='my-private-pairing-token-0123456789'
    original_config={'server_url':'http://127.0.0.1:8765',
        'token':token,'collection_id':'medical','device_label':'My PC',
        'auto_sync':False,'custom_option':42}
    (path/'config.json').write_text(json.dumps(original_config))
    original_meta={'config':{**original_config, 'user_selection':'Keep me'},
                   'mod': 19, 'disabled':False}
    (path/'meta.json').write_text(json.dumps(original_meta))
    monkeypatch.setenv('APPDATA',str(roaming))
    monkeypatch.setattr(bootstrap,'addon_archive',lambda:packaged_addon(tmp_path))
    assert 'installed' in bootstrap.ensure_anki_bridge()
    after_config=json.loads((path/'config.json').read_text())
    after_meta=json.loads((path/'meta.json').read_text())
    assert after_config['server_url']==LOCAL_URL
    assert after_meta['config']['server_url']==LOCAL_URL
    assert after_meta['config']['token']==token
    assert after_config['custom_option']==42
    assert after_meta['config']['user_selection']=='Keep me'
    assert after_meta['mod']==19
    assert bootstrap.ensure_anki_bridge()=='Anki desktop bridge installed'
    assert (path/'meta.json').is_file()


def test_an_existing_ankiconnect_socket_is_never_killed(tmp_path,monkeypatch):
    root=tmp_path/'Local';server=root/'AnkiCompanion'/'server'
    server.mkdir(parents=True)
    (server/'token.txt').write_text('valid-long-token-from-our-installation')
    monkeypatch.setenv('LOCALAPPDATA',str(root))
    monkeypatch.setattr(bootstrap.sys,'platform','win32')
    class FakeClient:
        def __init__(self,url,token):
            assert url=='http://127.0.0.1:8765'
        def request(self,path):
            raise ConnectionError('AnkiConnect is not our authenticated server')
    monkeypatch.setattr(bootstrap,'Client',FakeClient)
    monkeypatch.setattr(bootstrap.subprocess,'run',lambda *a,**k:pytest.fail('AnkiConnect must not be stopped'))
    assert bootstrap.retire_legacy_windows_server() is False


def test_retire_legacy_process_checks_exact_installed_executable(tmp_path,monkeypatch):
    home=tmp_path/'AppData'/'Local'
    data=home/'AnkiCompanion'/'server';data.mkdir(parents=True)
    (data/'token.txt').write_text('valid-long-token-from-our-installation')
    installed=tmp_path/'Programs'/'AnkiCompanionServer.exe';installed.parent.mkdir()
    installed.write_bytes(b'installed binary placeholder')
    monkeypatch.setenv('LOCALAPPDATA',str(home))
    monkeypatch.setattr(bootstrap.sys,'platform','win32')
    monkeypatch.setattr(bootstrap,'server_executable',lambda:installed)
    calls=[]
    class FakeClient:
        def __init__(self,url,token):
            assert url=='http://127.0.0.1:8765'
        def request(self,path):
            calls.append('probe')
            if len(calls)>1:raise ConnectionError('legacy service stopped')
            return {'streak':0}
    monkeypatch.setattr(bootstrap,'Client',FakeClient)
    def subprocess_run(args,**kwargs):
        assert args[0]=='powershell.exe'
        assert 'ExecutablePath' in args[-1]
        assert kwargs['env']['ANKICOMPANION_SERVER_BIN']==str(installed)
        calls.append('stop')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(bootstrap.subprocess,'run',subprocess_run)
    assert bootstrap.retire_legacy_windows_server() is True
    assert calls==['probe','stop','probe']


def test_new_local_port_is_consistent_with_packaged_installer_and_clients():
    root=Path(__file__).resolve().parents[1]
    assert LOCAL_URL=='http://127.0.0.1:8766'
    assert bootstrap.LOCAL_URL==LOCAL_URL
    assert '8766' in (root/'anki_addon/config.json').read_text()
    assert '8766' in (root/'anki_addon/bridge.py').read_text()
    assert "'8766' if sys.platform == 'win32' else '8765'" in (root/'server/main.py').read_text()
    assert '127.0.0.1:8766/health' in (root/'.github/workflows/ci.yml').read_text()
    assert 'reverse_proxy api:8765' in (root/'deployment/Caddyfile').read_text(), 'Hosted backend routing should remain unchanged'


def test_update_is_one_click_and_relaunches_only_on_update_switch():
    root=Path(__file__).resolve().parents[1]
    from companion import updates
    source=(root/'companion/updates.py').read_text()
    installer=(root/'installer/AnkiCompanion.iss').read_text()
    assert "'/AUTOUPDATE'" in source
    assert "'/VERYSILENT'" in source
    assert 'IsAutoUpdate' in installer
    assert 'GetCmdTail' in installer
    assert 'Check: IsAutoUpdate' in installer
    assert '\n// User data lives outside' in installer
    release=(root/'.github/workflows/auto-release.yml').read_text()
    candidate=(root/'.github/workflows/release-candidate.yml').read_text()
    assert 'publish: true' in release
    assert 'needs: [verification, assemble, signed-upgrade]' in candidate
    assert 'environment: production-release' in candidate


def test_optional_emulator_evidence_pull_does_not_override_passing_instrumentation():
    script=(Path(__file__).resolve().parents[1]/'scripts/check_android_emulator.sh').read_text()
    assert 'assert "OK (" in s and "FAILURES" not in s' in script
    assert 'if ! adb pull /sdcard/' in script
    assert 'evidence-pull-warning.txt' in script
