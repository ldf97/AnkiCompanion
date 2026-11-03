#!/usr/bin/env bash
# Two actual Android versions, one emulator, a UI-initiated update, no uninstall.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p test-results/update-buttons/http test-results/update-buttons/android
OUT="$PWD/test-results/update-buttons"
cd android
export APP_VERSION_CODE=970001 APP_VERSION_NAME=0.1.1
bash gradlew --no-daemon assembleDebug assembleDebugAndroidTest
cp app/build/outputs/apk/debug/app-debug.apk "$OUT/base-android.apk"
adb install -r "$OUT/base-android.apk"
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell am instrument -w -e upgrade_phase seed -e class \
  org.ankicompanion.app.UpgradeContinuityTest#seedOriginalData \
  org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner \
  | tee "$OUT/android/seed.txt"
grep -q 'OK (1 test)' "$OUT/android/seed.txt"
# The data-continuity fixture deliberately uses a minimal cached state.json that
# the full activity cannot display. Keep its exact bytes in the same private
# app sandbox during the GUI click, then restore before the OS upgrade.
adb shell run-as org.ankicompanion.app mv files/state.json files/ci-original-state.json

# Apply a harmless but visible code patch, and build the update with the SAME
# debug signer on the SAME emulator runner.
SRC=app/src/main/java/org/ankicompanion/app/MainActivity.kt
cp "$SRC" "$OUT/OriginalMainActivity.kt"
python3 - <<'PY'
from pathlib import Path
p=Path('app/src/main/java/org/ankicompanion/app/MainActivity.kt')
s=p.read_text()
old='updateButton=button("App updates · "+BuildConfig.VERSION_NAME)'
new='updateButton=button("App updates · PATCH CONFIRMED · "+BuildConfig.VERSION_NAME)'
assert old in s
p.write_text(s.replace(old,new))
PY
export APP_VERSION_CODE=970002 APP_VERSION_NAME=0.1.2
bash gradlew --no-daemon assembleDebug
cp app/build/outputs/apk/debug/app-debug.apk "$OUT/http/app-patched.apk"
mv "$OUT/OriginalMainActivity.kt" "$SRC"
python3 - <<'PY'
from pathlib import Path
import hashlib,json
root=Path('../test-results/update-buttons/http')
apk=root/'app-patched.apk'
release={
  'schema_version':1,'version':'0.1.2','build':970002,
  'commit':'two-version-button-acceptance',
  'assets':{'android':{'filename':'app-patched.apk','version_code':970002,
                       'size':apk.stat().st_size,
                       'sha256':hashlib.sha256(apk.read_bytes()).hexdigest()}}
}
(root/'update.json').write_text(json.dumps(release),encoding='utf-8')
print('Release fixture:',json.dumps(release,indent=2))
PY
cd ..
python3 -m http.server 8767 --bind 0.0.0.0 --directory "$OUT/http" >"$OUT/android/http-server.log" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
for n in {1..30}; do curl -fsS http://127.0.0.1:8767/update.json >/dev/null && break || sleep 1; done
adb shell appops set org.ankicompanion.app REQUEST_INSTALL_PACKAGES allow
# The test finds the actual Android GUI button, clicks it, checks the
# confirmation, verifies downloaded APK and waits for OS installer UI.
set +e
adb shell am instrument -w -e update_button_phase run -e class \
 org.ankicompanion.app.UpdateButtonClickTest#clickUpdateDownloadsAndOpensSystemInstaller \
 org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner \
 | tee "$OUT/android/update-click.txt"
INSTRUMENT_STATUS=${PIPESTATUS[0]}
set -e
if [[ "$INSTRUMENT_STATUS" != 0 ]] || ! grep -q 'OK (1 test)' "$OUT/android/update-click.txt"; then
  echo 'FAIL: actual Update button did not reach installer UI'
  exit 1
fi
adb pull /sdcard/Android/data/org.ankicompanion.app/files/update-button-acceptance.json "$OUT/android/button-evidence.json"
adb shell run-as org.ankicompanion.app cp files/ci-original-state.json files/state.json
# Complete the Android OS installer confirmation. This is a real package
# manager UI upgrade, not adb install -r.
for n in {1..45}; do
  adb shell uiautomator dump /sdcard/update-hierarchy.xml >/dev/null 2>&1 || true
  adb shell cat /sdcard/update-hierarchy.xml > "$OUT/android/installer-ui.xml" 2>/dev/null || true
  BUTTON=$(python3 - "$OUT/android/installer-ui.xml" <<'PY'
import sys,xml.etree.ElementTree as ET,re
try: root=ET.parse(sys.argv[1]).getroot()
except Exception: raise SystemExit()
for node in root.iter('node'):
  label=(node.attrib.get('text','')+' '+node.attrib.get('content-desc','')).strip().lower()
  b=node.attrib.get('bounds','')
  if (label in ('install','update','install anyway') and node.attrib.get('enabled')=='true'):
    points=list(map(int,re.findall(r'\d+',b)))
    if len(points)==4:
      print((points[0]+points[2])//2, (points[1]+points[3])//2)
      break
PY
)
  if [[ -n "$BUTTON" ]]; then
    echo "OS installer confirmation: $BUTTON"
    adb shell input tap $BUTTON
    break
  fi
  sleep 2
done
for n in {1..60}; do
  code=$(adb shell dumpsys package org.ankicompanion.app | grep -m1 'versionCode=' || true)
  if [[ "$code" == *'versionCode=970002'* ]]; then
    echo 'PASS: Android OS applied patched version 970002 without uninstall' | tee "$OUT/android/installed-result.txt"
    break
  fi
  sleep 2
done
grep -q 'PASS' "$OUT/android/installed-result.txt"
# Existing test verifies preserved pairing, Anki review outbox, settings, state, Eren bytes.
adb shell am instrument -w -e upgrade_phase verify -e class \
  org.ankicompanion.app.UpgradeContinuityTest#verifyDataAfterInPlaceUpgrade \
  org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner \
  | tee "$OUT/android/continuity.txt"
grep -q 'OK (1 test)' "$OUT/android/continuity.txt"
# The continuity fixture intentionally keeps a minimal saved state, which is not
# a valid full UI snapshot. Verify the PATCH CONFIRMED code change in the exact
# updated APK's DEX instead of trying to render that incomplete cached state.
python3 - "$OUT/base-android.apk" "$OUT/http/app-patched.apk" <<'PY'
import sys,zipfile
def contains_patch(path):
    with zipfile.ZipFile(path) as apk:
        return any(b'PATCH CONFIRMED' in apk.read(name)
                   for name in apk.namelist() if name.endswith('.dex'))
assert not contains_patch(sys.argv[1]), 'Baseline APK already contains the patch'
assert contains_patch(sys.argv[2]), 'Updated APK is missing the code patch'
print('PASS: installer installed the genuinely patched APK, not a rebuilt identical binary')
PY
echo 'PASS: clicked Android Update, checked real SHA+signer, installed patch and preserved data'
