# Pong Update Lab · v1.0.0

This is a separate, deliberately tiny Windows + Android update experiment. It contains **only Pong and its update button**. No Anki executable, sync server, AnkiDroid integration, or personal data.

- Windows: Electron/NSIS, using the same `electron-updater` check/download/install API as Nexus Mods Vortex. An installed NSIS app is necessary for in-place updates; the provided `.exe` is its installer.
- Android: Kotlin/OkHttp streaming download and Android's package installer, following the Mihon update pathway. Package: `com.ankicompanion.ponglab`.
- Release channel: a separate **prerelease** tag, `pong-update-lab`, inside `ldf97/AnkiCompanion`. It intentionally does **not** use the repository's `releases/latest` API or overwrite the actual AnkiCompanion release.
- Both clients check `https://github.com/ldf97/AnkiCompanion/releases/download/pong-update-lab/` and the corresponding `latest.yml` / `pong-android.json` metadata.
- On future updates, increment the version in `VERSION.json`, `windows/package.json`, and `android/app/build.gradle.kts` (including Android's versionCode). GitHub Actions then replaces the channel assets while keeping the same test signing certificate.
- The Android demo certificate is **public and intentionally insecure**. This is acceptable for a disposable toy app but is NEVER appropriate for AnkiCompanion production or sensitive apps; anybody could sign an APK with the disclosed key. **Do not use the demo certificate outside this isolated experiment.**
- Install the Windows setup exe and the Android APK **only from the Pong channel**, not the normal AnkiCompanion latest release.
