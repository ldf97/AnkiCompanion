# AnkiCompanion

## Final October 31 CI / personal package status

The corrected AnkiDroid reviewer-startup code at [bca4582](https://github.com/ldf97/AnkiCompanion/commit/bca4582fb65d008e85c500165b002b20cffbd065) **passed all six jobs** in [run 41132639476](https://github.com/ldf97/AnkiCompanion/actions/runs/41132639476), including the full 20 desktop → 10 phone → 20 desktop native synchronization test, 50 distinct reviews, matching tested scheduling fields, and automatically observed 30/50 and 50/50 on both platforms. The earlier dock-era rerun [41130929265](https://github.com/ldf97/AnkiCompanion/actions/runs/41130929265) had failed because of the initial reviewer WebView race; this has been corrected and retested.

A **separately delivered personal Eren-ready bundle** now includes the original 30 image/skin files and 19 quotes, the working Windows installer, both Android APKs, the Anki desktop add-on, a one-click Windows import/activation wrapper, and passing CI evidence. The owner does **not** need to reacquire the artwork or start with a blank theme. This public repository intentionally does not publish the original private art/quotes or user credentials.

The personal wrapper's authenticated skin import/export/activation test passed; the device-specific Windows PowerShell launcher itself, owner's actual phone/launcher, AnkiWeb and Tailscale pairing, offline/screen-off behavior and production signing/in-place updates remain unverified. Exact-record redo after an undo is not implemented end-to-end. **No production release is published.** The passing native APK is a debug build and may have a different signature from an installed development APK.

AnkiCompanion provides a native Windows app and compact dock, Android app and home-screen widget, FastAPI/SQLite server, Anki desktop add-on, and separate AnkiDroid Companion edition. Closing the desktop window opens the dock; Open restores it. The original hollow/lit tray flame has the streak number BELOW it.

## Install

Use [the connection guide](deployment/CONNECT.md). Windows installers and Android packages are GitHub Actions development artifacts; no production release has been published. The owner's private checkpoint includes the personal skin, source and saved evidence.

Install the Windows package and **both** Android packages: AnkiCompanion and AnkiDroid Companion. The latter installs beside stock AnkiDroid. Sign in to the same AnkiWeb account on desktop Anki and AnkiDroid Companion and resolve the initial full-sync direction. Install the supplied desktop add-on. Connect both companion apps/add-on to the same authenticated HTTPS server and collection ID. The guide supplies a private Tailscale HTTPS setup.

The companion server counts review events; Anki's native sync service synchronizes collections and schedules. The AnkiDroid extension implements a permission-protected history and sync-status API. These endpoints are not assumed to exist in stock AnkiDroid.

## Verified behavior

The full **20 desktop → 10 phone → 20 desktop** sequence passed in [CI run 41074197807](https://github.com/ldf97/AnkiCompanion/actions/runs/41074197807), source `c9d674852257ef3704f4a52a8218c9fe2c5a1e06`. Both collections started synchronized with zero reviews. Actual AnkiDroid reviewer UI answered the phone cards. A real Android AppWidgetHost received system-delivered updates; the desktop app's production timer fetched state automatically. Both displayed 30/50 (60%, 20 remaining), then 50/50 and completion. Native comparison matched 50 distinct review/card identities and all tested scheduling fields, each card reviewed once. No manual sync or refresh was used after initial setup.

This is **Android emulator + real desktop Anki backend verification**, not the owner's physical phone or Windows Anki GUI. Native synchronization used Anki's local sync server, not the owner's AnkiWeb account. The compact dock now also displays progress counts, percentage, remaining total and connection status; its checks are included in subsequent CI.

Other checks cover 28 Python tests, HTTPS authentication/certificate enforcement, retry/deduplication, undo, update validation, Windows installer installation/server health, Qt tray/docking rendering, Android tests/lint, and API 35 widget warning animation. Successful builds alone are not synchronization proof.

## Use and updates

Enable **Live widget updates** while studying for five-second polling with a foreground notification. Without it, Android background work runs approximately every 15 minutes and may be deferred. Android may stop a long data-sync session after six hours. Remote study commands use a notification when Android prohibits background activity launching.

Both apps discover stable GitHub Releases automatically and provide an Update button. Source commits alone are not installable updates. Checks cover hashes, Android package/signing identity, and Windows Authenticode publisher identity. The [signed candidate workflow](.github/workflows/release-candidate.yml) requires persistent signing keys and does not publish. Development Windows artifacts are unsigned; Android artifacts use debug keys. Windows builds are automatically published to GitHub Releases after successful main-branch CI. Android builds are added to those releases only when a stable private signing key is configured; physical-device in-place upgrade acceptance remains unverified. See [update setup](deployment/UPDATES.md).

## Build and reproduce

- Server/desktop: Python 3.12; install `requirements-desktop.txt`. Run `python -m server.main` and `python -m desktop.app`. The pairing token is created in the private data folder.
- Android companion: JDK 17, SDK 35; `cd android && bash gradlew testDebugUnitTest assembleDebug lintDebug`.
- Windows installer: PyInstaller and Inno Setup 6; `scripts/build_windows.ps1`.
- AnkiDroid Companion: [pinned upstream and overlay](ankidroid_bridge/README.md); JDK 21 / SDK 36. The workflow builds the separate application ID and test APK.
- Full acceptance: `scripts/check_cross_device.sh`, run by CI on API 35, saves instrumentation logs, screenshots, payloads and native comparison results.

Private character artwork, quotes, credentials and user data are excluded. Public builds use an independent neutral skin; personal packs import without replacing their assets. Keep signing keys and pairing tokens outside git.

Use `python scripts/run_logged.py UNIQUE-LOG.txt -- COMMAND...` to save test output and an atomic continuation ZIP. Physical devices, screen-off latency, the user's accounts/network, and production signed update installation remain separate acceptance checks.

