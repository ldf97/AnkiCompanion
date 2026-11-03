#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../android"
bash gradlew --no-daemon installDebug installDebugAndroidTest
mkdir -p app/build/emulator-evidence
adb shell am instrument -w org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner | tee app/build/emulator-evidence/instrumentation.txt
python3 -c 'from pathlib import Path; s=Path("app/build/emulator-evidence/instrumentation.txt").read_text(); assert "OK (" in s and "FAILURES" not in s, s'
# Dedicated randomized-streak visual acceptance on one REAL Android emulator.
# Two UI screenshots are captured by UiAutomation, not generated illustrations.
if [[ "${1:-}" == "35" ]]; then
  adb shell am instrument -w -e class org.ankicompanion.app.WidgetStreakTransitionTest \
    org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner \
    | tee app/build/emulator-evidence/streak-instrumentation.txt
  grep -q 'OK (1 test)' app/build/emulator-evidence/streak-instrumentation.txt
fi
# Evidence copying is diagnostic only. On API28 the emulator can shut down
# AFTER instrumentation reports OK, making adb pull fail despite passing tests.
# Preserve the substantive instrumentation result instead of a false CI fail.
if ! adb pull /sdcard/Android/data/org.ankicompanion.app/files/evidence app/build/emulator-evidence/; then
  printf 'Optional evidence pull unavailable after passing instrumentation tests\n' > app/build/emulator-evidence/evidence-pull-warning.txt
fi
if [[ "${1:-}" == "35" ]]; then
  # Screenshot extraction is REQUIRED for the requested visual acceptance.
  # A passing test without captured images is not sufficient evidence.
  for picture in before.png after.png widget-before.png widget-after.png result.json; do
    test -s "app/build/emulator-evidence/evidence/streak-random/$picture" || {
      echo "Missing actual Android screenshot/evidence: $picture" >&2
      exit 1
    }
  done
fi


# Same-signer in-place Android upgrade acceptance, not reinstall/restore.
# Use only API35 to keep the 4-emulator CI matrix affordable.
if [[ "${1:-}" == "35" ]]; then
  adb shell am instrument -w -e upgrade_phase seed -e class \
    org.ankicompanion.app.UpgradeContinuityTest#seedOriginalData \
    org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner \
    | tee app/build/emulator-evidence/update-seed.txt
  grep -q 'OK (1 test)' app/build/emulator-evidence/update-seed.txt
  APP_VERSION_CODE=2 APP_VERSION_NAME=0.1.2 bash gradlew --no-daemon assembleDebug
  # adb install -r is the actual operating-system no-uninstall upgrade.
  adb install -r app/build/outputs/apk/debug/app-debug.apk \
    | tee app/build/emulator-evidence/inplace-install.txt
  grep -q 'Success' app/build/emulator-evidence/inplace-install.txt
  adb shell am instrument -w -e upgrade_phase verify -e class \
    org.ankicompanion.app.UpgradeContinuityTest#verifyDataAfterInPlaceUpgrade \
    org.ankicompanion.app.test/androidx.test.runner.AndroidJUnitRunner \
    | tee app/build/emulator-evidence/update-verify.txt
  grep -q 'OK (1 test)' app/build/emulator-evidence/update-verify.txt
fi