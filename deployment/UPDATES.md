# Direct GitHub application updates

Both operating systems update from public GitHub Releases in this existing repository. No
additional updater service, account, Google Play listing, Microsoft Store listing, or
owner-operated PowerShell command is needed. Updating the source branch alone does
not update installed applications: GitHub must have a newer published release.

## Windows

- The PySide6 **App updates** button checks
  `https://github.com/ldf97/AnkiCompanion/releases/latest/download/update.json`
  independently of the local study server, pairing token, and port 8766.
- It compares the installed version, downloads the Windows Inno Setup executable
  from the same GitHub release, enforces its declared byte count and SHA-256,
  and verifies it again before starting the ordinary Windows installer.
- The installer replaces the bundled desktop program, local server and packaged
  Anki bridge, while keeping the local study database and pairing token outside
  the program directory. A verified backup is taken before installation.
- An optional Windows Authenticode publisher pin is enforced if that build has
  configured one. Buying/configuring a signing certificate is **not required**
  for the SHA-256-verified GitHub-release update path. The optional check currently
  uses PowerShell internally; users never have to run a command.
- The update button has its own persistent status and a visible error dialog.
  Local study-server connection failures cannot hide its check/download errors.

## Android

- Both the Android Companion and the separately packaged AnkiDroid Companion
  fetch the same public GitHub release manifest. No paired Windows server is
  involved in application updates.
- APK downloads are checked for size, SHA-256, Android package identity,
  increasing version code, and compatible installed signing identity before
  passing the APK to Android's own package installer.
- Android requires the user to approve app installation from this source once
  (if not already allowed) and confirm installation. The app resumes a verified
  downloaded APK after that permission is granted.
- Android's security model **requires** an existing package's release signing
  identity to remain compatible across updates. This is not a paid service or
  an optional permission we can bypass; the existing CI release key must
  remain stable. A debug APK signed with a different key cannot overwrite
  the user's release APK without migration.

## Publishing and verification

The existing GitHub Actions build/release workflow packages Windows and both
Android APKs, along with a shared `update.json`. CI verifies packaging and
checks upgrade behavior on disposable Windows/Android environments. Production
signing material, where required, remains in existing GitHub secrets rather
than in the app or source repository.

A published update must have its installer/APKs and matching manifest; installing
onto an existing device is the final acceptance test. Never uninstall the
existing app to get around a signing error: preserve the study database,
native Anki review history, and private skins.
