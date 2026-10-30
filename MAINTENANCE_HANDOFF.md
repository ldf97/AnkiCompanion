# AnkiCompanion

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

Both apps discover stable GitHub Releases automatically and provide an Update button. Source commits alone are not installable updates. Checks cover hashes, Android package/signing identity, and Windows Authenticode publisher identity. The [signed candidate workflow](.github/workflows/release-candidate.yml) requires persistent signing keys and does not publish. Development Windows artifacts are unsigned; Android artifacts use debug keys. Production in-place updating remains unverified until persistent signing identities and devices are available. See [update setup](deployment/UPDATES.md).

## Build and reproduce

- Server/desktop: Python 3.12; install `requirements-desktop.txt`. Run `python -m server.main` and `python -m desktop.app`. The pairing token is created in the private data folder.
- Android companion: JDK 17, SDK 35; `cd android && bash gradlew testDebugUnitTest assembleDebug lintDebug`.
- Windows installer: PyInstaller and Inno Setup 6; `scripts/build_windows.ps1`.
- AnkiDroid Companion: [pinned upstream and overlay](ankidroid_bridge/README.md); JDK 21 / SDK 36. The workflow builds the separate application ID and test APK.
- Full acceptance: `scripts/check_cross_device.sh`, run by CI on API 35, saves instrumentation logs, screenshots, payloads and native comparison results.

Private character artwork, quotes, credentials and user data are excluded. Public builds use an independent neutral skin; personal packs import without replacing their assets. Keep signing keys and pairing tokens outside git.

Use `python scripts/run_logged.py UNIQUE-LOG.txt -- COMMAND...` to save test output and an atomic continuation ZIP. Physical devices, screen-off latency, the user's accounts/network, and production signed update installation remain separate acceptance checks.

