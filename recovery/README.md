# AnkiCompanion Recovery v1 — frozen safety hatch

These recovery tools remain independent of AnkiCompanion. They do not load the installed app, its code, its server or its updater. Once released, recovery-v1 assets are never overwritten.

**Windows:** Download AnkiCompanion-Recovery.exe once. Keep it on your Desktop or another folder *outside* the AnkiCompanion installation. Double-click, then click Repair / reinstall. It downloads the latest stable GitHub release manifest, verifies the installer size and SHA-256, and opens the installer. The old app need not run.

**Android:** Install AnkiCompanion-Recovery.apk once. It is a separate application (org.ankicompanion.recovery) with its own launcher icon. It retrieves the latest stable APK, verifies its checksum, package ID and pinned AnkiCompanion certificate, and opens Android's native APK installer. Android still requires user installation approval and compatible signing for the existing AnkiCompanion app.

**Unchanged release:** GitHub tag **ankicompanion-recovery-v1** is a separate prerelease; the publishing workflow refuses to overwrite it. New regular app releases do not affect this tag or its binaries. The Android recovery app has its own disposable demo signing key, and it does not share the main app's package ID or data.

No recovery program can guarantee operation if GitHub is unavailable, the OS removes required functionality, the user's network fails, or published production packages become invalid. This tool does not delete app data, and cannot override Android signing protections.
