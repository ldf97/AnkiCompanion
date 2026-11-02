# AnkiCompanion — Requirements #22–#28 incremental workspace checkpoint

Source branch: `feature/hosted-portable-signing-windows-sim-20261101`.
Do not merge or publish until full CI, signing, real-device upgrade and Anki acceptance complete; the original Eren assets, credentials and installed profiles remain private.

## One-sentence solutions
22. Give every device the same server-confirmed shared-state revision and distinguish cached or provisional progress.
23. Keep study history and settings outside replaceable binaries and test preservation across restart/upgrade.
24. Update compatible binary packages in place without restoring databases, skins, credentials or queues.
25. Gate publication on CI acceptance, consistent signing and explicit release authorization.
26. Verify official downloads in the app before invoking OS-managed in-place installation.
27. Provide GUI setup, bridge self-repair and error recovery with no scripts required from the owner.
28. Preserve user settings, identities, credentials, skins and pending reviews with crash-safe storage and tests.

**Ledger checkmarks mean code written + focused local tests, NOT a production update or physical-device acceptance.**

## Sequential work ledger
- [x] **22**: Shared SHA-256 revision from confirmed state, displayed by desktop/Android; local `pytest tests/test_server.py -k shared_revision` passed (2 tests).
- [x] **23**: Server now fails closed if an existing database is missing its token or required schema/settings; local restart and data-retention tests verify the original bytes, history, shared revision and owner artwork survive updates.
- [x] **24**: The Windows in-app updater now creates and verifies a transactional SQLite/token/private-skin backup *before* launching an in-place installer, and rejects unsafe upgrades without asking for a restore; same-signer Android upgrade retention was already tested in emulator.
- [x] **25**: Direct and automatic candidate workflows now require the entire reusable CI suite, fail when persistent signing secrets are absent, demand both production-signed Android packages, and only publish after an explicit approved release dispatch.
- [x] **26**: Android resumes the already verified APK after the OS install-source permission screen without downloading again, preserving native installer confirmation; Windows already downloads, SHA-verifies and launches the release from the in-app Update button.
- [x] **27**: Windows GUI now offers one-click Repair setup and automatically retries installing the safely packaged Anki bridge every 10 minutes, retaining hosted pairing and avoiding terminal instructions; Android handles system permissions in its own interface.
- [x] **28**: Encrypted Android exceptional-signing recovery now includes byte-exact private skin files with integrity/path/overwrite checks, alongside the prior encrypted connection, preferences and durable pending outbox; a new emulator test validates restored artwork after deletion.

## External acceptance limitations
Google Compute Engine billing/project and private-state migration remain unprovisioned; the actual phone's Android signing certificate is unknown; physical-device acceptance remains outstanding.

## Workspace recovery
The GitHub Actions `.github/workflows/workspace-snapshot.yml` generates a `resumable-workspace-source` ZIP with branch commit SHA after each push; local workspace is `/mnt/data/AnkiCompanion-workspace`.

## Upload checkpoints (GitHub PR #9)
- 22: `2acccfd5ed81f765fdf993e260e85db60642b198`
- 23: `75e23234d5056d3c56d9de45d3d5792ef984ca95`
- 24: `7014e58b5eafd2d9ffd903b6bf4afa339e731c53`
- 25: `28f140447f7b87a3e1bbe94ae62cccb86117f4a3`
- 26: `56368b5196df9cabe26eeafbbebdf2d551305017`
- 27: `5aa051507f6e19b1c1aafc7d8827e8bfbe65fe3d`
- 28: `7b75fc04a5b69ae5587b9d011e54b894e35c8dfa`

## Last local test command
`python -m pytest -q tests/test_server.py tests/test_updates.py tests/test_desktop_bootstrap.py tests/test_portability_release.py tests/test_hosted_deployment.py --maxfail=1`
Result: **72 passed** on the workspace (Python 3.13); includes stable ordering for shared revisions and test-only Windows crash.log lock tolerance. The GitHub Actions Android instrumentation, Windows installer, native Anki and cross-device results on the exact final SHA must still be checked.

## Recovery if the assistant freezes
1. Download the attached full workspace ZIP or GitHub `resumable-workspace-source` artifact on the latest commit.
2. Read this document, then compare files against PR #9 and the last successful GitHub Actions run.
3. Never use an unsigned/new-signer APK to replace the existing phone installation, nor overwrite original Eren art/token/database during updates.
4. Resume with any failing CI job logs, then verify Android private artwork recovery with the new `PortabilityTest` and the Windows real Anki smoke.

## Windows CI cleanup follow-up
The real Windows Anki/AQt process reached its `PASS: real Anki/AQt opened` line, but `TemporaryDirectory` cleanup failed on Anki's temporarily locked `crash.log` (WinError 32); the CI-only launcher now uses `ignore_cleanup_errors=True` to avoid treating unrelated temporary cleanup as a product failure.
