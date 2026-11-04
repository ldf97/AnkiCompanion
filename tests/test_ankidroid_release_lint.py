"""Release-only AnkiDroid lint regression checks.

Debug builds can pass while release lintVital blocks publication; keep
application-context lifecycle ownership and sync timestamp explicit.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ankidroid_companion_release_lint_integration():
    source = (ROOT / "ankidroid_bridge/CompanionIntegration.kt").read_text()
    assert 'import android.annotation.SuppressLint' in source
    assert source.count('@SuppressLint("StaticFieldLeak")') >= 2
    assert 'app = context.applicationContext' in source
    assert '.putLong("synced_ms", java.time.Instant.now().toEpochMilli())' in source
    assert '.putLong("synced_ms", System.currentTimeMillis())' not in source


def test_signed_version_dispatch_supports_existing_release_series():
    workflow = (ROOT / ".github/workflows/owner-release-trigger.yml").read_text()
    assert "3 <= int(build) <= 1000000000" in workflow
    assert "gh workflow run release-candidate.yml" in workflow
