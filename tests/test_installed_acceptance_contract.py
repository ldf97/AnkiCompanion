"""Prove that CI checks installed Windows binary, emulator upgrades, native Anki state."""
from pathlib import Path
import json
import pytest
from scripts.assert_cross_device_evidence import verify

ROOT=Path(__file__).resolve().parents[1]


def test_real_installation_gate_and_native_evidence_present():
    ci=(ROOT/'.github/workflows/ci.yml').read_text()
    assert 'Launch actual installed Windows companion desktop' in ci
    assert 'python scripts/ci_windows_installed_app.py' in ci
    assert 'python scripts/assert_cross_device_evidence.py' in ci
    assert 'needs: [python, android, ankidroid, gcp-infrastructure, windows, emulator, cross-device]' in ci
    assert "'$result'" not in ci  # Shell status is evaluated, never hard-coded.
    assert "if [ \"$result\" != 'success' ]" in ci
    assert 'adb install -r' in (ROOT/'scripts/check_android_emulator.sh').read_text()
    script=(ROOT/'scripts/ci_windows_installed_app.py').read_text()
    assert "'Programs'/'AnkiCompanion'/'desktop'/'AnkiCompanion.exe'" in script
    assert 'process.poll() is not None' in script


def test_cross_device_evidence_rejects_false_positive(tmp_path):
    data=dict(phone_widget30=True,desktop_widget30=True,phone_widget50=True,
              desktop_widget50=True,matched=True,phone_finished=True,
              observer_finished=True,phase=50)
    rows=dict(reviews=[[i+1,i+1,4,1,0] for i in range(50)],
              cards=[[i+1,0,2,i+1,1,1,0] for i in range(50)])
    (tmp_path/'PASS.json').write_text(json.dumps(data))
    (tmp_path/'matching-native-collections.json').write_text(json.dumps(rows))
    assert verify(tmp_path)['review_count']==50
    data['desktop_widget50']=False
    (tmp_path/'PASS.json').write_text(json.dumps(data))
    with pytest.raises(AssertionError,match='unfinished'):
        verify(tmp_path)
    data['desktop_widget50']=True
    (tmp_path/'PASS.json').write_text(json.dumps(data))
    rows['cards'][0][5]=2
    (tmp_path/'matching-native-collections.json').write_text(json.dumps(rows))
    with pytest.raises(AssertionError,match='scheduling'):
        verify(tmp_path)