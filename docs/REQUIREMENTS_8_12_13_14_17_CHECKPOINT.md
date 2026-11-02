# AnkiCompanion group 1 checkpoint — #8, #12, #13, #14, #17

Base main: `d025900d1de04483d6ea232ef705651a1f0e9d6b` (merged PR #10).
Date: 2026-11-02. User-confirmed behavior: native undo must synchronize, but study accountability/streak is *not* reversed by undo.

## Changes and acceptance
- Desktop native `state_did_undo` hook triggers immediate bounded history reconciliation, and only genuine removed revlog rows enqueue scheduling retractions.
- Native Anki/AnkiDroid collections remain authoritative for schedule and due dates; server issues scoped wakeups on retractions and verified native sync receipts.
- Immutable answered-event ledger counts unique real study attempts for daily goals/streaks even after undo; retracted flags and `progress.active_reviews` report native review state separately.
- Android cached/provisional progress also retains undone attempts for accountability.
- Android online study handoff drains local outbox, runs native Anki sync, reports ticket/revision, and checks for intervening device updates.
- Android offline study falls back to AnkiDroid local queue and durable outbox without pretending it is synchronized; retry is scheduled.
- Windows online handoff defers until native revision is current, and handles initial/full-sync direction conflicts with bounded exponential retry instead of repeated background loops.
- Android JobScheduler uses retry/backoff, refreshes state after native sync, and distinguishes automatic transient failures from full-sync conflicts.
- Three-device server notifications, undo idempotency, out-of-order send, previous-day streak retention and Windows optional hook isolation covered in tests.

## Tests
- Local `python -m pytest -q tests --ignore=tests/test_native_anki.py --disable-warnings --maxfail=1`: 129 passed, 1 skipped.
- `python -m compileall -q anki_addon server companion desktop tests`: PASS.
- Native Anki and Android tests require GitHub CI (local system has no installed native Anki/Android SDK); these source changes are not yet CI-verified.

## Honest limits
- <5 sec was established previously for local long-poll dispatch, not end-to-end native scheduling across WAN, doze, or Android lifecycle.
- Native three-device physical PC1↔phone↔PC2 simultaneous-use acceptance remains unverified.
- Anki full-sync conflict requires a direction choice in native Anki; never automatically overwrite local/remote data.
- Existing private skins, local user data, production signing and real cloud infrastructure were not accessed or modified.
- Source archive is a resumable sanitized workspace, not an APK or a completed production deployment.

## Changed-file fingerprints
- `anki_addon/__init__.py`: `18486966a745db47038dcf3c5fee4854a238f575`
- `anki_addon/bridge.py`: `751bcd6c8b97ba8a8200740714a8652300aaac89`
- `anki_addon/history.py`: `5d85fab9addbf5d8234e2fc6f2f9d063436b03ea`
- `companion/status.py`: `de7c4bf5c9f7745ad4c4b158f0b9333b436a382e`
- `android/app/src/main/java/org/ankicompanion/app/Sync.kt`: `644f660ddea6ccfdb22a66cb147bc9dac934081f`
- `android/app/src/main/java/org/ankicompanion/app/MainActivity.kt`: `e20cf4db8b971c8968386144833fbf197081a702`
- `android/app/src/main/java/org/ankicompanion/app/Outbox.kt`: `4b73591e1ecf41d0cc44c35f97615f347b7ee0d3`
- `server/store.py`: `552843508bd7566aaad9e65bee87faad381c5f1d`
- `tests/test_server.py`: `67cd4467628bac6a0aed0b4a848a641834b3969d`
- `tests/test_progress_acceptance.py`: `fee961161ae7e099b673337859ace061ea536c09`
- `tests/test_windows_launcher_sim.py`: `b73be928fd262468e809141ae737be391b663a03`
- `tests/test_undo_streak_native_sync.py`: `f8e5d13ab51ca4008f30b4fdc772cb27f71c088f`
