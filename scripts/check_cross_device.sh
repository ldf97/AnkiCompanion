#!/usr/bin/env bash
set -euo pipefail
mkdir -p test-results/cross-device
python scripts/emulator_backend.py >test-results/cross-device/backend.log 2>&1 &
backend_pid=$!
trap 'adb logcat -d >test-results/cross-device/logcat.txt 2>/dev/null || true; kill "$backend_pid" "${observer_pid:-}" 2>/dev/null || true' EXIT
python - <<'PY'
import time,urllib.request
for _ in range(120):
 try:
  urllib.request.urlopen('http://127.0.0.1:8766/health').read();break
 except OSError:time.sleep(1)
else:raise RuntimeError('Acceptance backend did not start')
PY
python scripts/emulator_desktop_observer.py >test-results/cross-device/desktop.log 2>&1 &
observer_pid=$!
adb install -r ankidroid-upstream/AnkiDroid/build/outputs/apk/full/debug/AnkiDroid-full-x86_64-debug.apk
adb install -r ankidroid-upstream/AnkiDroid/build/outputs/apk/androidTest/full/debug/AnkiDroid-full-debug-androidTest.apk
(cd android && bash gradlew --no-daemon installDebug installDebugAndroidTest)
adb shell pm grant org.ankicompanion.app com.ichi2.anki.companion.debug.permission.READ_WRITE_DATABASE
adb shell pm grant org.ankicompanion.app android.permission.POST_NOTIFICATIONS
adb shell appops set --uid com.ichi2.anki.companion.debug MANAGE_EXTERNAL_STORAGE allow
adb shell am instrument -w -e class com.ichi2.anki.CompanionAcceptanceTest com.ichi2.anki.tests/com.ichi2.testutils.NewCollectionPathTestRunner >test-results/cross-device/ankidroid-instrumentation.txt 2>&1 &
phone_pid=$!
python - <<'PY'
import time,urllib.request,json
for _ in range(180):
 s=json.load(urllib.request.urlopen('http://127.0.0.1:8766/test/status'))
 if s['phone_ready']:break
 time.sleep(1)
else:raise RuntimeError('AnkiDroid initial collection download failed')
PY
adb shell am instrument -w -e crossDevice true -e class org.ankicompanion.app.CrossDeviceTest org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner | tee test-results/cross-device/companion-instrumentation.txt
wait "$phone_pid"
adb pull /sdcard/Android/data/org.ankicompanion.app/files/evidence test-results/cross-device/
adb logcat -d >test-results/cross-device/logcat.txt
python - <<'PY'
from pathlib import Path
import json,time,urllib.request
r=Path('test-results/cross-device')
for name in ['ankidroid-instrumentation.txt','companion-instrumentation.txt']:
 s=(r/name).read_text();assert 'OK (1 test)' in s and 'FAILURES' not in s,s
for _ in range(30):
 s=json.load(urllib.request.urlopen('http://127.0.0.1:8766/test/status'))
 if all(s[k] for k in ['phone_widget30','desktop_widget30','phone_widget50','desktop_widget50','matched']):break
 time.sleep(1)
else:raise RuntimeError(s)
(r/'PASS.json').write_text(json.dumps(s,indent=2))
print('PASS: actual AnkiDroid UI + Anki native backend: 20/10/20; automatic 30/50 and 50/50 widgets; matching revlog and scheduling.')
print('Environment: Android emulator and Linux Qt offscreen. Physical Windows/Android devices remain unverified.')
PY
