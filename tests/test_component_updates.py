"""A release updates 5 installed components through 3 OS-managed packages."""
from pathlib import Path
import json
from scripts.release_manifest import make
from scripts.stamp_component_versions import stamp
from companion.updates import component_update_summary
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_release_manifest_names_every_installed_component(tmp_path):
    for filename in ('AnkiCompanion-Windows-Setup.exe','AnkiCompanion-source.zip',
                     'AnkiCompanion-Android.apk','AnkiDroid-Companion-Android.apk'):
        (tmp_path/filename).write_bytes(filename.encode())
    result=make(tmp_path,'1.4.3',117,'a'*40)
    assert set(result['components'])=={
        'windows_desktop','local_server','anki_desktop_addon',
        'android_companion','ankidroid_companion'}
    assert len(set(x['asset'] for x in result['components'].values()))==3
    for spec in result['components'].values():
        assert spec['version']=='1.4.3'
        assert spec['asset'] in result['assets']
    summary=component_update_summary({'components':result['components']},remote_server=True)
    assert 'Hosted server: updated through Google Cloud deployment' in summary
    assert 'Android Companion: separate signed update on the phone' in summary
    assert 'AnkiDroid Companion: separate signed update on the phone' in summary


def test_addon_manifest_is_stamped_in_release_workspace_only(tmp_path):
    addon=tmp_path/'anki_addon';addon.mkdir()
    manifest={'name':'Anki Companion Bridge','package':'anki_companion_bridge','version':'0.1.0'}
    (addon/'manifest.json').write_text(json.dumps(manifest))
    assert stamp('2.5.7',tmp_path)=='2.5.7'
    assert json.loads((addon/'manifest.json').read_text())['version']=='2.5.7'
    with pytest.raises(ValueError):stamp('INVALID',tmp_path)
    assert json.loads((addon/'manifest.json').read_text())['version']=='2.5.7'
    workflow=(ROOT/'.github/workflows/release-candidate.yml').read_text()
    assert 'python scripts/stamp_component_versions.py --version $env:RELEASE_VERSION' in workflow


def test_separate_android_updates_are_exposed_in_client():
    android=(ROOT/'android/app/src/main/java/org/ankicompanion/app/MainActivity.kt').read_text()
    assert 'private lateinit var ankidroidUpdateButton:Button' in android
    assert 'Update Android Companion to ' in android
    assert 'Update AnkiDroid Companion to ' in android
    assert 'ankidroid-update.json' in android
    windows=(ROOT/'desktop/app.py').read_text()
    assert 'component_update_summary' in windows
    assert 'remote_server=first_run.has_remote_connection(self.config)' in windows


def test_release_manifest_refuses_to_omit_any_installed_component(tmp_path):
    sources=('AnkiCompanion-Windows-Setup.exe','AnkiCompanion-source.zip',
             'AnkiCompanion-Android.apk','AnkiDroid-Companion-Android.apk')
    for filename in sources:(tmp_path/filename).write_bytes(filename.encode())
    for filename in sources:
        missing=tmp_path/filename
        missing.unlink()
        with pytest.raises(ValueError,match='Missing required signed release input'):
            make(tmp_path,'1.4.3',117,'a'*40)
        missing.write_bytes(filename.encode())