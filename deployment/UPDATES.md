# Update architecture: Vortex (Windows) + Mihon (Android)

The updater uses the existing public GitHub repository and releases. No separate
hosting, Microsoft Store, Google Play listing, new user account or paid signing
subscription is needed. The Windows release is an Electron/NSIS installer and
the two Android applications use native Android APK installation.

## Windows: electron-updater + NSIS

- The PySide6 study GUI no longer contacts a server or downloads application
  installers. Its **App updates** button launches the installed
  `AnkiCompanion.exe --updates` Electron shell and closes the study GUI.
- The Electron shell is also the regular launcher for the bundled Python
  study GUI and server. `updater/main.js` implements the same core
  `electron-updater` calls as Vortex:
  `autoUpdater.checkForUpdates()`, `downloadUpdate()`,
  `quitAndInstall()`. The updater shows progress and errors.
- `electron-builder` packages a Windows per-user NSIS installer; it
  generates `latest.yml` with SHA-512 and the NSIS `.blockmap` in
  addition to `AnkiCompanion-Windows-Setup.exe`.
- The existing release workflow publishes these files to GitHub Releases.
  Installer code lives beneath `resources/desktop/` and `resources/server/`;
  study data/pairing remains beneath `%LOCALAPPDATA%/AnkiCompanion/server/`
  and is not overwritten.
- The installed server's separate `--backup-before-update` command performs a
  checked backup. Electron requests authenticated loopback shutdown of the
  local server prior to NSIS replacing its files.
- Windows Authenticode signing is optional. If a certificate already exists
  in GitHub Actions secrets, electron-builder signs **before** generating
  SHA-512 metadata. A Windows SmartScreen warning may occur on unsigned builds.
- Existing Inno Setup installations lack the Electron shell and **cannot
  self-upgrade using this architecture**. A single installation of the new
  NSIS release is required to transition. The existing study database is
  kept outside the program installation folder. Verify shortcut migration
  and preserved data on a real owner device before marking transition done.

## Android: OkHttp + Android installer

- The companion and separate AnkiDroid Companion both check public GitHub
  Releases directly without a local Windows server or pairing.
- Like Mihon, `Updates.kt` uses OkHttp for release discovery and streamed
  APK downloads, with UI progress. APK size/SHA-256, package ID, increasing
  version code and installed signing identity are checked.
- Android's own package installer applies the update after one-time
  unknown-apps permission (if needed) and a normal install confirmation.
- Existing Android apps **must** be upgraded with the same signing identity
  or a valid Android certificate rotation lineage. No new payment or account
  is required, but this OS security rule cannot be bypassed.

## Tests / release gate

The Windows acceptance workflow builds an installed Electron NSIS package
and checks its metadata and bundled components. The Android workflow exercises
the app's real update button in an emulator. A newly installed version A
to version B native upgrade (Windows and Android), including review and
pairing continuity, remains the final acceptance standard.

Do not merge/publish solely because source-level checks pass. Running
source from a GitHub branch does not replace already-installed application
binaries; publish a higher version and test the installed binary first.
