# AnkiCompanion Group 1: three-device gym lab checkpoint

Date: 2026-11-02. Base: main `d2c6da1152e979b81013e83bbb4f1d33ed326027` (PR #11).

- Added an executable three-device gym simulation `simulations/gym/lab.py`: PC1, phone, PC2 have separate persistent SQLite review/outbox and native-schedule-model files, and speak to a real authenticated FastAPI server in a separate Python process. A native scheduling model is **not the actual Anki sync server**. Model tests **do not** prove cellular/OS scheduling behavior.
- Added `tests/test_group1_gym_lab.py` to the normal Python suite; one complete gym scenario simulates 20 PC1 reviews, a pre-study phone sync, rapid targeted HTTP notification, gym blackout, 15 queued phone attempts with 1 undo, phone-process restart, 5 different PC2 attempts, lost HTTP acknowledgment after server commit, replay without duplicate review, successful three-client convergence, real HTTP server restart, then a stale same-card concurrent-edit conflict without data loss.
- Added `tests/test_native_three_device_gym.py` (requires real Anki 26.9.3, automatically installed on GitHub CI) to verify the native scheduler and revlog converge between three Anki collections through a real native Anki sync server, including offline phone-model undo and streak credit. The existing separate CI cross-device Android emulator job verifies real AnkiDroid/desktop integration.
- Added `.github/workflows/ci.yml` step to generate and upload repeatable model evidence `test-results/group1-gym/gym-lab-report.json` after normal Python suite.
- Existing prod code was preserved while test coverage expands. **Issue discovered by gym simulation:** an answer followed by undo rotates native `outgoing_ticket`; stale client ticket leaves unacknowledged source dirty. The tested client refreshes the latest server ticket before publishing, matching the existing production Android/desktop paths. Future changes must preserve this rule.
- Local actual-HTTP model run: **PASS**, targeted change notification 0.204 seconds, three-device reconnection/reconciliation 0.044 seconds (loopback scheduling model), 41 study attempts and 40 active native reviews before the conflict injection; both concurrent conflicting answers preserved as study attempts, second scheduling edit unacknowledged pending human conflict handling.
- Local Python tests excluding unavailable native Anki module: **130 passed, 1 skipped** (2026-11-02). CI on exact commit still required before merge.
- **Unresolved external acceptance:** real-world mobile carrier/Doze, always-online server deployment, actual owner devices. A low-latency local simulated result is *not* a 5-second real native-synchronization guarantee.

## First native CI finding

GitHub run 41511882095 reached the native Python test and failed at HTTP 401 because the new test fixture omitted its own Authorization header; the server correctly refused unauthenticated requests. The source fixture now sends its ephemeral test-only bearer token. This error did not establish a native sync failure; rerun CI on the corrected exact SHA.
