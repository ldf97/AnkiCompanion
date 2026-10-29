# AnkiCompanion maintenance handoff (2026-10-29)

**IMPORTANT:** This public GitHub repository currently contains a bootstrap commit, **not the complete application source**. The complete sanitized source is preserved in the ChatGPT artifact `AnkiCompanion_GitHub_Source_Sanitized.zip`; the complete project and maintenance checkpoint are in `AnkiCompanion_Maintenance_Handoff.zip`. Upload the source-only archive's contents to this repository before treating this as a buildable checkout.

The prepared maintenance checkpoint includes:
- Offline GitHub update tests, with 22 existing/new server tests passing.
- Corrected project README.
- Windows setup, server launcher, and desktop launcher scripts (not yet executed on Windows).

Remaining work:
- Tray icon: existing lit/hollow flame SVG with streak number **BELOW** the flame.
- Native Anki/AnkiDroid card sync and companion progress sync, including 20 desktop + 10 phone + 20 desktop of 50.
- Real-device verification, update distribution, and GitHub Actions/release automation.

No production release has been authorized. Keep Eren/anime imagery and personal quote assets out of the public repository; do not commit secrets, user data, or compiled packages. Preserve the original full project checkpoint.
