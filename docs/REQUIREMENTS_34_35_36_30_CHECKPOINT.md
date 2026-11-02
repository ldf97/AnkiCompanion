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