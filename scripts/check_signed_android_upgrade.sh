#!/usr/bin/env bash
set -euo pipefail
# Called only with production-signed release candidates, never CI debug APKs.
mkdir -p test-results/signed-upgrade
if [[ ! -f candidate/AnkiCompanion-Android.apk || ! -f candidate/AnkiDroid-Companion-Android.apk ]]; then
  echo 'No production-signed Android candidate; update acceptance cannot be asserted.'
  exit 0
fi
sha256sum candidate/*.apk >test-results/signed-upgrade/candidates.sha256
old=test-results/signed-upgrade/AnkiCompanion-v1.0.9.apk
curl -fLsS --retry 3 --connect-timeout 20 --max-time 90 \
  https://github.com/ldf97/AnkiCompanion/releases/download/v1.0.9/AnkiCompanion-Android.apk -o "$old"
echo '155d2ea31e68ac81571527dc279845ebaf5637de1c954f656e0f8557be84dfa4  '"$old" | sha256sum -c -
# Android itself is the authority for signer compatibility; no replacement
# custom certificate logic can override the OS package manager.
adb install "$old" | tee test-results/signed-upgrade/old-install.txt
adb install -r candidate/AnkiCompanion-Android.apk | tee test-results/signed-upgrade/in-place-upgrade.txt
grep -q 'Success' test-results/signed-upgrade/in-place-upgrade.txt
adb install candidate/AnkiDroid-Companion-Android.apk | tee test-results/signed-upgrade/ankidroid-production-install.txt
grep -q 'Success' test-results/signed-upgrade/ankidroid-production-install.txt
adb shell pm list packages | grep -q 'org.ankicompanion.app'
adb shell pm list packages | grep -q 'com.ichi2.anki.companion'
adb shell dumpsys package org.ankicompanion.app | grep -m 1 versionCode >test-results/signed-upgrade/new-companion-version.txt
adb shell dumpsys package com.ichi2.anki.companion | grep -m 1 versionCode >test-results/signed-upgrade/new-ankidroid-version.txt
printf 'PASS: Android accepted signed v1.0.9 -> candidate replacement without uninstall.\n'
