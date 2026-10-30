#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../android"
bash gradlew --no-daemon connectedDebugAndroidTest
mkdir -p app/build/emulator-evidence
adb pull /sdcard/Android/data/org.ankicompanion.app/files/evidence app/build/emulator-evidence/
