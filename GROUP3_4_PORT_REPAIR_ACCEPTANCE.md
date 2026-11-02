# AnkiCompanion — Group 3, Group 4, AnkiConnect regression fix

Date: 2026-11-02. This checkpoint is source implementation and local regression evidence, **not** proof of installation on the owner's PC/phone.

## Repairs

- **#34 reopened — AnkiConnect collision:** AnkiConnect retains TCP `127.0.0.1:8765`. The packaged Windows AnkiCompanion server listens on `127.0.0.1:8766`. Linux/hosted Docker remains on its existing internal port `8765`. The desktop, add-on defaults, Windows bootstrap, repair/tunnel commands and Windows CI smoke checks consistently use `8766` locally.
- **Existing user settings:** Only exact old loopback `8765` endpoints are migrated. Hosted/LAN URLs are not rewritten. The desktop preserves unrelated connection keys. Anki's existing add-on `config.json` / `meta.json` configuration, including pairing tokens, deck selection and user preferences, is preserved. The add-on is installed atomically; the user's collection is never modified by installation.
- **Existing old server:** GUI/startup repair only attempts to stop `AnkiCompanionServer.exe` when an authenticated *old Companion server* answers on `8765` using the saved existing token. It then requires an exact installed executable-path match before stopping the process; it never stops AnkiConnect or an unknown owner of the port. If retirement cannot be verified, repair surfaces an error instead of killing an arbitrary process.
- **#25 build / sign / publish:** GitHub `main` workflow now requests publication after the exact-commit verification suite, persistent Android signing checks, complete signed release manifest, emulator signed-upgrade acceptance, and production environment protection. Missing signing keys result in a documented deferred release, not a counterfeit/debug production APK. Release promotion still depends on GitHub environment approvals and external keys.
- **#26 point-and-click update:** The Windows Update control downloads the official SHA-256 verified release, snapshots existing data automatically, and launches a quiet in-place installer. The installer selectively relaunches the server and UI after `/AUTOUPDATE`. Android keeps OS-mediated APK installation and signer continuity checks.
- **#27 no owner-run scripts:** Routine installation/repair/update is exposed through the GUI. Internal PowerShell is only invoked *by the app* to identify and retire its own authenticated legacy Windows server; no shell commands are required from the owner.
- **#37 hands-off maintenance:** The Windows GUI rechecks local server health every 60 seconds and repairs a stopped server. The bridge is repaired every 10 minutes without overwriting custom settings, startup bootstraps the local service, and update notifications are deduplicated per release. Hosted connections are preserved and are never replaced by local bootstrap.

## Tests

- Local available suite: `python -m pytest -q tests --ignore=tests/test_native_anki.py --ignore=tests/test_native_three_device_gym.py` → **148 passed, 1 skipped**.
- Focused port/migration/installer tests pass, including non-interference with AnkiConnect, idempotent Anki config migration and exact executable match.
- The remaining two tests require a separately installed `anki` Python package not present in this environment; the Windows GUI, Inno Setup compiler, Android emulator and physical-device smoke cannot execute locally here. GitHub CI's Windows test now reserves `8765` while launching installed Companion server on `8766`.

## Still not production-accepted

1. Actual post-upgrade Anki + AnkiConnect + AnkiCompanion operation on owner's Windows laptop; owner has not installed a corrected signed release.
2. Production signing credentials, signing compatibility with the owner's currently installed Android APK, final Android in-place upgrade acceptance and protected production release configuration.
3. Physical-device unattended app/background behavior, shutdown/restart while reviews are in progress, and hosted server deployment.

**Do not claim these remainings as solved.** Source changes may be PR-tested and merged, but a merged source fix is not automatically deployed to the owner's computer.
