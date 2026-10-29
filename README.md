# AnkiCompanion

Native Python/PySide6 Windows companion, Kotlin Android app and home widget, FastAPI/SQLite server, and Anki desktop add-on. Development work in progress; physical Windows/AnkiDroid synchronization acceptance has **not** passed.

## Run from source

Use Python 3.12. Install `requirements-desktop.txt`. Run `python -m server.main` and `python -m desktop.app` in separate terminals. Configure the URL and pairing token from `data/token.txt`; never commit this token. Package the add-on with `python scripts/package_addon.py`, install the resulting `.ankiaddon` into Anki, then configure its server URL/token and the same collection ID. See [secure network setup](deployment/CONNECT.md).

The private personal character pack is intentionally excluded. Import it from your private checkpoint via the Skins dialog. Public builds include a separate neutral skin and retain the modular skin importer.

## Build

- Android: JDK 17, Android SDK 35, `cd android && bash gradlew testDebugUnitTest assembleDebug lintDebug`.
- Windows: Python dependencies plus PyInstaller and Inno Setup 6; run `scripts/build_windows.ps1`. Creates a per-user installer with desktop app, server, add-on and connection instructions. Updates preserve user data.
- GitHub Actions builds development installers/APKs and uploads test reports. It does not publish a production release. Debug APK signing keys may differ across machines/runs; debug artifacts are not a stable update channel.

## Verified and unverified

Server tests cover progress, retry deduplication, undo tombstones, settings/day boundaries, packs and update metadata. A native integration test uses **two real Anki 26.9.3 backends and Anki's local sync server** for 20 → 30 → 50 answers, comparing review histories and card scheduling. This is not a physical AnkiDroid test. Qt offscreen checks verify flame-above-number rendering, progress and dock restoration; they do not prove Windows shell behavior.

Stock AnkiDroid has no public full review-history feed. Unverified custom provider calls are disabled by default. Phone review totals reach the companion after native sync and desktop ingestion. Foreground `DO_SYNC` is available through **Sync AnkiDroid**; it has no completion callback. Seamless automatic handoff while reviewers remain open is not guaranteed. Background study commands use a notification because Android restricts automatic activity launches.

The widget uses a launcher-hosted ViewFlipper for the warning pulse. **Live widget updates** is an explicit study session with a foreground notification; Android may stop it after six hours. Otherwise refresh is best-effort periodic work. Actual launcher animation, sleep/background behavior, device networking and Windows shell behavior still require device acceptance.

## Continue without losing work

Run `python scripts/run_logged.py NEW-LOG-NAME.txt -- COMMAND...` for local checks. It preserves output/exit status and creates an atomic continuation ZIP. Keep full private checkpoints separate from the public repository. Record written, unit-tested, native-backend-tested, emulator-tested and physical-device-tested results separately. Never infer the last two from a successful build. Never publish a production release without explicit authorization.
