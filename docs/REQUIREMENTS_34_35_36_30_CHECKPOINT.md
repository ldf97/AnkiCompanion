# AnkiCompanion sequential checkpoint: requirements 34, 35, 36, 30

Timestamp: 2026-11-02. GitHub PR #9 on branch `feature/hosted-portable-signing-windows-sim-20261101`.

## One-sentence implementation solutions
- **34**: Ensure optional add-on failures are isolated from Anki startup and prove an actual Windows Anki GUI launch without allowing the test runner's Qt shutdown artifacts to produce false errors.
- **35**: Expose separately the server's confirmed state, this device's pending reviews and native scheduling receipt, connectivity age and other devices' native sync status without declaring a stale snapshot synchronized.
- **36**: Exercise actual installed Windows binaries, installed Android package upgrades, and the AnkiDroid/Anki cross-device review path in CI, retaining every result artifact and distinguishing emulator from physical hardware.
- **30**: Make one versioned release manifest enumerate every independently installed component and surface updates per component in the GUI with safe, platform-native install paths.

## Sequential ledger
- [x] 34 — CI checks that the *actual loaded* add-on registered the review hook and writes a JSON acceptance record before bypassing only the disposable Qt/Python atexit crash; local regression tests pass, cloud Windows check pending.
- [x] 35 — server includes snapshot age and online/offline status alongside native revision receipts; Android and Windows show those separately from provisional local answers and cached/offline state, with regression tests passing.
- [x] 36 — CI now executes the actual installed Windows desktop binary after repeated Inno upgrades, asserts native 50/50 review+schedule evidence and app widgets, and gates all required platform tests; Android signing/hardware still require physical acceptance.
- [x] 30 — release manifests enumerate Windows desktop, local server, Anki add-on and both Android apps; Windows version-stamps the bundled Anki add-on, desktop UI distinguishes local versus hosted server updates, and Android displays independent upgrade buttons for each package.

### Validation and release policy
GitHub Actions run 41484525881: Python, Android, AnkiDroid, API28/33/35/36 emulator, Google Cloud infra, and native cross-device passed; Windows Anki GUI printed PASS but test runner had a transient Qt atexit failure and returned nonzero. The fixes here are not yet production installed. No production merge/release, no private Eren art, credentials or personal profiles in this public source.

### Recovery
This directory is a real editable source workspace and Git repository; after each source commit a ZIP and updated ledger will be retained, and the exact source diff uploaded to PR #9. Never replace an existing APK with an incompatible signature or silently reset original user data.

## CI failure correction and final acceptance tightening (current continuation)

- **#34:** Latest Windows CI reached real Anki/AQt startup, then failed because Anki 26.09's generated `reviewer_did_answer_card` hook object is **not iterable**; `scripts/ci_windows_anki_launcher.py` now asserts `hook.count()` and checks its generated `_hooks` callback registry for `anki_companion_bridge` (upstream source `pylib/tools/hookslib.py`, Anki 26.09.3). Test `test_real_anki_hook_is_noniterable_generated_object` passes locally; Windows CI must validate this change.
- **#36:** `desktop/app.py` emits a narrowly scoped test-only GUI-ready marker from a queued Qt event-loop callback (CI only), and `scripts/ci_windows_installed_app.py` rejects a process that is merely alive but never initialized a Qt window, also checking actual process PID and startup evidence.
- **#30:** `scripts/release_manifest.py` refuses to create a complete release missing **either** Android signed APK or the Windows/source packages; this matches the existing release publication gate and avoids an unannounced partial release.
- **Local validation:** 108 tests passed, 1 skipped (this local Python environment has no PySide6; GitHub CI installs it); Python compilation passed. Native Anki, physical phone/laptop and private signer checks are not established by these local tests.
- **Deployment remains independent:** No hosted Google Compute Engine instance or signed production release has been provisioned. Do not merge/release until exact-head GitHub CI accepts Windows and native Android cross-device.