"""Regression for the v1.0.11 Android 10,000,000 versionCode mistake."""
import pytest
from scripts.release_build_codes import next_build, verify_upgrade


def manifest(version, android_code):
    return {
        "version": version,
        "assets": {
            "android": {"version_code": android_code},
            "ankidroid": {"version_code": 220_000_000 + android_code},
        },
    }


def test_new_release_can_replace_installed_v1_0_11():
    # Despite v1.0.13 being the latest versionName, Android is still
    # running v1.0.11 at build 10,000,000 on many phones.
    previous = manifest("1.0.13", 1_000_031)
    candidate = manifest("1.0.14", next_build(previous, 35))
    verify_upgrade(previous, candidate)
    assert candidate["assets"]["android"]["version_code"] > 10_000_000
    assert candidate["assets"]["ankidroid"]["version_code"] > 230_000_000


def test_old_release_code_regression_is_blocked():
    previous = manifest("1.0.13", 1_000_031)
    with pytest.raises(ValueError, match="Android versionCode regression"):
        verify_upgrade(previous, manifest("1.0.14", 1_000_032))


def test_next_build_increases_over_existing_high_code():
    previous = manifest("1.0.15", 10_000_500)
    assert next_build(previous, 40) == 10_000_501


def test_reject_nonascending_semver_even_if_code_is_new():
    with pytest.raises(ValueError, match="not newer"):
        verify_upgrade(manifest("1.0.13", 1_000_031),
                       manifest("1.0.13", 10_000_900))
