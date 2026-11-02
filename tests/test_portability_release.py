"""Platform/packaging gates; physical signer identity still needs actual device."""
from pathlib import Path
import tempfile
import pytest
from scripts.release_manifest import make
ROOT=Path(__file__).resolve().parents[1]

def test_two_independent_android_apks_share_immutable_release_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        for name in ('AnkiCompanion-Android.apk','AnkiDroid-Companion-Android.apk',
                     'AnkiCompanion-Windows-Setup.exe','AnkiCompanion-source.zip'):
            (folder/name).write_bytes(name.encode())
        result=make(folder,'1.0.10',1000234,'e'*40)
        assert set(result['assets'])=={'android','ankidroid','windows','source'}
        assert result['assets']['android']['version_code']==1000234
        assert result['assets']['ankidroid']['version_code']==221000234
        assert result['assets']['ankidroid']['sha256']!=result['assets']['android']['sha256']

def test_ankidroid_is_production_release_not_another_ephemeral_debug_apk():
    workflow=(ROOT/'.github/workflows/release-candidate.yml').read_text()
    overlay=(ROOT/'ankidroid_bridge/apply.py').read_text()
    assert ':AnkiDroid:assembleFullRelease' in workflow
    assert 'KEYSTOREPATH' in workflow and 'KEYSTOREPWD' in workflow
    assert "com.ichi2.anki.companion'" in workflow
    assert 'AnkiDroid-Companion-Android.apk' in workflow
    assert 'ANKIDROID_COMPANION_BUILD' in overlay
    assert "('android' in manifest['assets']) == ('ankidroid' in manifest['assets'])" in workflow

def test_android_self_updater_exposes_portable_recovery_and_both_packages():
    updates=(ROOT/'android/app/src/main/java/org/ankicompanion/app/Updates.kt').read_text()
    portable=(ROOT/'android/app/src/main/java/org/ankicompanion/app/Portability.kt').read_text()
    main=(ROOT/'android/app/src/main/java/org/ankicompanion/app/MainActivity.kt').read_text()
    assert 'fun checkAnkiDroid' in updates
    assert 'signingCertificateHistory' in updates
    assert 'AES/GCM/NoPadding' in portable
    assert 'PBKDF2WithHmacSHA256' in portable
    assert 'Restore recovery' in main and 'Export recovery' in main


def test_android_pre_29_outbox_explicitly_implements_closeable():
    source=(Path(__file__).resolve().parents[1]/"android/app/src/main/java/org/ankicompanion/app/Outbox.kt").read_text()
    assert 'SQLiteOpenHelper(context,"reviews.db",null,1),java.io.Closeable' in source
