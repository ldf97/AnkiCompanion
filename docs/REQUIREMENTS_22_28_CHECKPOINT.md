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

## Sequential work ledger
- [x] **22**: Shared SHA-256 revision from confirmed state, displayed by desktop/Android; local `pytest tests/test_server.py -k shared_revision` passed (2 tests).
- [x] **23**: Server now fails closed if an existing database is missing its token or required schema/settings; local restart and data-retention tests verify the original bytes, history, shared revision and owner artwork survive updates.
- [ ] **24**: Not started.
- [ ] **25**: Not started.
- [ ] **26**: Not started.
- [ ] **27**: Not started.
- [ ] **28**: Not started.

## External acceptance limitations
Google Compute Engine billing/project and private-state migration remain unprovisioned; the actual phone's Android signing certificate is unknown; physical-device acceptance remains outstanding.

## Workspace recovery
The GitHub Actions `.github/workflows/workspace-snapshot.yml` generates a `resumable-workspace-source` ZIP with branch commit SHA after each push; local workspace is `/mnt/data/AnkiCompanion-workspace`.
