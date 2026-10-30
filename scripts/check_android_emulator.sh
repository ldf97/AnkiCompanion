#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../android"
bash gradlew --no-daemon installDebug installDebugAndroidTest
mkdir -p app/build/emulator-evidence
adb shell am instrument -w org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner | tee app/build/emulator-evidence/instrumentation.txt
python3 -c 'from pathlib import Path; s=Path("app/build/emulator-evidence/instrumentation.txt").read_text(); assert "OK (" in s and "FAILURES" not in s, s'
adb pull /sdcard/Android/data/org.ankicompanion.app/files/evidence app/build/emulator-evidence/
