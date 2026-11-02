# AnkiCompanion — resumable checkpoint for #34, #35, #36, #30

**Date:** November 2, 2026
**Repository:** https://github.com/ldf97/AnkiCompanion
**Pull request:** https://github.com/ldf97/AnkiCompanion/pull/9
**Development branch:** `feature/hosted-portable-signing-windows-sim-20261101`
**GitHub HEAD:** `082dc39a53e266200b1f45875cb85009dea319b4`
**Latest full CI:** https://github.com/ldf97/AnkiCompanion/actions/runs/41490504033

## Sequential solutions and saved commits

1. **#34 Anki launcher safety:** Verify the real Windows Anki GUI loaded the companion review callback and record positive evidence before the disposable Qt test process bypasses its unrelated native atexit failure; [commit 6e5dc07](https://github.com/ldf97/AnkiCompanion/commit/6e5dc0700cdcb4ef3d9f602339206d2ba4b69d28).
2. **#35 Real synchronization indicators:** Show observed online/offline age, native Anki scheduling revision receipts, confirmed server progress, and provisional local outbox state separately; [commit c52fc18](https://github.com/ldf97/AnkiCompanion/commit/c52fc18bcc752443729ae6bb141b9d8c657aee3a).
3. **#36 Installed-app acceptance:** Launch the real Inno-installed Windows desktop after a repeat in-place update, verify exactly 50 native reviews/schedules and both widget checkpoints, and reject releases unless every CI platform passes; [commit cb21a1a](https://github.com/ldf97/AnkiCompanion/commit/cb21a1a2e0aab3bddf34d5c542e553259c2cb239).
4. **#30 Coordinated component updates:** Version and identify Windows desktop, local server, Anki desktop add-on, Android Companion, and AnkiDroid Companion within one release manifest while retaining separate platform-native phone installers and hosted-server deployment; [commit 082dc39](https://github.com/ldf97/AnkiCompanion/commit/082dc39a53e266200b1f45875cb85009dea319b4).

## Tests and honesty of acceptance

- Local: **106 Python tests passed**, omitting `tests/test_native_anki.py` because the external `anki` Python package is not installed in the offline workspace; this is **not** a claim that native Anki tests passed locally.
- Local: Python compileall and YAML loading passed; 2 acceptance-contract tests, 3 component-release tests and status/launcher tests included.
- GitHub CI at the HEAD above is **not yet confirmed green**: use the exact Actions link, inspect Windows installed desktop/Anki GUI, Android API28/33/35/36, cross-device native scheduling and the final `acceptance` job.
- Anki native scheduling and 20 desktop + 10 phone + 20 desktop convergence **did pass earlier emulator/backend integration**; new checks require exact exported artifacts to pass too.
- No code has been merged to `main`, no new production release or physical-device installation, and no real hosted Google Cloud instance has been deployed.
- The actual phone's signing certificate and production signing continuity remain an **external blocker**; do not uninstall, reset, or install a differently signed APK in place.
- **Private Eren artwork, credentials, original Anki collections, pairing tokens, fonts and personal user data are excluded from this source ZIP.**

## Resume procedure

Open this ZIP as an ordinary project, then inspect `docs/REQUIREMENTS_34_35_36_30_CHECKPOINT.md` and the current CI run. Continue by fixing any failing CI job in a local source copy, running the focused tests, committing/uploading changes to the existing PR without merging, and saving a fresh workspace ZIP. Production acceptance requires a compatible signed APK, physical Windows/Android testing and authorization to deploy the cloud server.

## Local test command

`python -m pytest -q tests --ignore=tests/test_native_anki.py --maxfail=1`

## Current continuation — 2026-11-02

A new regression run revealed that upstream Anki 26.09.3's generated reviewer hook is not iterable; the Windows Anki GUI had started successfully, then the smoke test itself threw `TypeError`. The fix reads the actual hook's generated `_hooks` callbacks after checking `.count()`; no user profile or add-on runtime code was changed.

I also strengthened the actual installed desktop acceptance by waiting for an explicit Qt event-loop initialization marker, and prevented incomplete release manifests from advertising a coordinated release while omitting a signed Android package. Local test result: 108 passed, 1 skipped due to local absence of PySide6. The exact GitHub acceptance run after these changes must be checked; no installed device or production release has been changed.