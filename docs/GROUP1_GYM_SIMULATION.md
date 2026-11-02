# Group 1: Gym simulation and native acceptance

**Source branch:** based on merged PR #11 (`d2c6da1152e979b81013e83bbb4f1d33ed326027`). Scope: #8, #12, #13, #14, #17. No production devices, Anki profiles, private artwork, credentials, or signing keys accessed.

## Lab topology

```
PC1 (its own SQLite) ─┐
                      ├── authenticated HTTP ── FastAPI server process ── persistent SQLite
Phone (its own SQLite)│                          │
                      │                     native sync controller
PC2 (its own SQLite) ─┘                          │
                               conflict-aware SQLite scheduling model (local test)
```

The **local** `simulations/gym/lab.py` uses three independent durable device files, actual HTTP requests to a separate spawned FastAPI server, a persisted scheduling/sync-hub model, simulated network partitions and post-commit packet loss. It is intentionally labeled a **model**, not a full Android OS or the proprietary AnkiWeb native protocol.

The CI Python suite separately runs `tests/test_native_three_device_gym.py`: three **real Anki 26.9.3 collections**, an ephemeral genuine Anki native sync server, native scheduler/revlog diffs, phone-model offline review and undo, and the actual companion server's streak/accountability logic. The existing GitHub `cross-device` job also exercises the real installed AnkiDroid Companion on an Android emulator and a Linux Qt desktop observer.

## Gym scenario, exact acceptance predicates

1. At home PC1 reviews 20 cards. The phone downloads the native schedule *before* opening study.
2. A second PC receives a change notification via authenticated long polling within 5s **on the local test network**.
3. Phone enters gym, loses network, answers 15 cards and undoes 1. Studying is not blocked; its outbox persists through phone-app process restart.
4. PC2 studies 5 **different** cards while the phone remains offline.
5. On reconnect the phone loses an HTTP response *after* server commit, retries, and uploads without duplicate accountability or lost undos. Native schedule converges across all three devices; 41 unique attempts, 40 active scheduled card reviews (20+1+15+5; 1 undone).
6. The actual HTTP server process restarts using the original SQLite disk. Auth, activity totals and applied native-revision receipts survive.
7. PC1 and PC2 concurrently answer the same card from stale copies. The second attempted native upload must **not silently overwrite** PC1's review; the conflicting local record and pending sync ticket survive, awaiting native conflict resolution. Both study attempts remain counted in the accountability ledger.

The native Anki CI scenario covers three native collections and 40 distinct attempts including one undo, resulting in 39 native revlog entries, with every card scheduler/revlog identical across all three replicas. The local model scenario has 41 attempts before the explicit conflict test because of its additional notification review.

## Run (automated)

```bash
python -m pytest -q tests/test_group1_gym_lab.py
python -m simulations.gym.lab --output test-results/group1-gym
# On GitHub with native Anki 26.9.3 installed:
python -m pytest -q tests/test_native_three_device_gym.py
```

The CI Python job produces a `test-results/group1-gym` report. **A green emulator/model test is not a guarantee of sub-5-second native sync on cellular, Android Doze wakeups, or on the owner's physical devices.** Network propagation, actual native Anki collection sync and study accountability are distinct clocks and outcomes. Actual full-sync conflicts can require a native direction choice; never silently discard either side.
