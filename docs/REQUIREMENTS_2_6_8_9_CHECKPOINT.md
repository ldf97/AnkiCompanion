# AnkiCompanion — requirements #2, #6, #8, #9 continuation

Date: 2026-11-02. Starting point: PR #9 merge `f6530dce69c0d3a7630132be5a79cbf5238d7fd9` on `main`. New work is staged separately; **do not publish a production release based on unverified owner hardware**.

- **#2 Every card answer is observed:** an answer increments a monotonic generation at the Anki review hook before delayed history reconciliation. Each committed answer retains its own identity in the outbox; newer answers cannot disappear when an older native synchronization finishes.
- **#6 Each answer initiates synchronization:** a worker tracks scanned, server-uploaded and natively-synced answer generations. A finished sync can acknowledge only the generation already uploaded **before that sync started**; any later answer remains pending for a new asynchronous sync. Existing AnkiDroid reviewer hooks and durable outbox remain untouched.
- **#8 Five-second response target:** an authenticated server long-poll (max 4 seconds; 200ms wake intervals) and dedicated desktop watcher add event-driven wakeups to existing desktop 2-second and Android live-session 1-second polling. A local two-client regression asserts dispatch under five seconds. **This does not guarantee cross-device native Anki scheduling under five seconds on arbitrary networks, OS sleep/background restrictions or AnkiWeb latency**.
- **#9 Server dispatches changes to other devices:** persistent SQLite `change_sequence` increments atomically on new/enriched answers, undo, changed settings, completed native upload tickets and commands. `GET /v1/changes?since=N&wait_ms=3500` is token-authenticated, bounded, returns change/reset indicators but no review/private contents, survives restart and works across server workers. The Anki desktop add-on long-polls and triggers its existing sync pipeline. Android continues to receive live foreground updates through existing 1-second polling; Android background delivery remains subject to OS scheduling.

Additional correctness improvement: idempotent undo retries no longer rotate the pending native-upload ticket, avoiding false rejection of an in-flight legitimate sync.

### Local tests and review evidence

`python -m pytest -q tests --ignore=tests/test_native_anki.py --maxfail=1` → **115 passed, 1 skipped**. `tests/test_native_anki.py` relies on the external native `anki` package unavailable in this offline workspace. These tests include 5-second local two-client dispatch, restart/cursor persistence, unauthorized request rejection, no duplicate wakeups, per-answer overlap, and undo ticket retry.

**CI not yet validated for this new branch:** run Windows real Anki GUI, Python, Android/AnkiDroid builds and native 20→10→20 cross-device acceptance on exact new commit. The previous 11/11 green run was on the **pre-change** commit `0e2954c8` and cannot be used as proof that these new changes passed on Windows or Android. No physical devices, live Google Cloud host, production signing key or installed app were changed.

User assets excluded: private Eren art, tokens, credentials, live Anki profiles and signed APK keys.
