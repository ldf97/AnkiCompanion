"""Android release versionCode safety: never downgrade an installed app.

v1.0.11 was signed and published with Android versionCode 10_000_000,
but v1.0.12 / v1.0.13 inadvertently used 1_000_030 / 1_000_031.
Android treats those releases as downgrades regardless of versionName.
"""
import argparse
import json
import re
from pathlib import Path

LEGACY_ANDROID_CODE_FLOOR = 10_000_000
ANKIDROID_OFFSET = 220_000_000


def component_codes(manifest):
    assets = manifest["assets"]
    return (int(assets["android"]["version_code"]),
            int(assets["ankidroid"]["version_code"]))


def next_build(previous, run_number):
    if run_number < 1:
        raise ValueError("Invalid workflow run number")
    android, ankidroid = component_codes(previous)
    return max(LEGACY_ANDROID_CODE_FLOOR + run_number,
               android + 1, ankidroid - ANKIDROID_OFFSET + 1)


def verify_upgrade(previous, candidate):
    older, newer = previous["version"], candidate["version"]
    def semver(value):
        if not re.fullmatch(r"\d+\.\d+\.\d+", value):
            raise ValueError("Invalid release version")
        return tuple(map(int, value.split(".")))

    if semver(newer) <= semver(older):
        raise ValueError(f"New release version {newer} is not newer than {older}")

    old_android, old_anki = component_codes(previous)
    new_android, new_anki = component_codes(candidate)
    if new_android <= max(old_android, LEGACY_ANDROID_CODE_FLOOR):
        raise ValueError(
            f"Android versionCode regression: candidate {new_android}, "
            f"latest {old_android}, legacy installed floor {LEGACY_ANDROID_CODE_FLOOR}")
    if new_anki <= max(old_anki, ANKIDROID_OFFSET + LEGACY_ANDROID_CODE_FLOOR):
        raise ValueError(
            f"AnkiDroid versionCode regression: candidate {new_anki}, "
            f"latest {old_anki}, legacy installed floor "
            f"{ANKIDROID_OFFSET + LEGACY_ANDROID_CODE_FLOOR}")
    if new_anki != ANKIDROID_OFFSET + new_android:
        raise ValueError("Companion APKs have inconsistent build numbers")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("next", "verify"))
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--run-number", type=int)
    args = parser.parse_args()
    previous = json.loads(args.previous.read_text())
    if args.command == "next":
        if args.run_number is None:
            parser.error("--run-number is required for next")
        print(f"build={next_build(previous, args.run_number)}")
    else:
        if args.candidate is None:
            parser.error("--candidate is required for verify")
        verify_upgrade(previous, json.loads(args.candidate.read_text()))
        print("PASS: both Android APK versionCodes strictly increase without data migration")


if __name__ == "__main__":
    main()
