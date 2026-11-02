# AnkiCompanion: requirements #2, #6, #8, #9, #10

Source checkpoint: 2026-11-02; starting point PR #10 commit `8758feb92ea79ac6f4d842c34c02e00fe1070b62`, following merged PR #9.

## Implemented changes

- **#2, observe answers:** Windows add-on packaging and the bootstrap validator now include `review_epoch.py` and precisely agree on the package contents. This fixes the observed Windows CI failure (`Bundled desktop bridge did not pass validation`) introduced by the earlier change. A new packaging/install regression validates the real ZIP, imports, and installed files. Anki's existing crash-isolated review callback stays the observation point.
- **#6, every answer starts sync work:** the native Anki reviewer hook increments a generation immediately; durable revlog/outbox reconciliation and the asynchronous worker follow. Native sync never acknowledges answers that arrived during a prior native sync. A batch of 1,000 events no longer falsely marks a larger pending outbox as fully sent. AnkiDroid continues to initiate background native synchronization from the committed reviewer operation, with a retry loop for overlapping answers.
- **#8, sub-five-second online notification target:** the bounded authenticated server long-poll reacts to SQLite commits on a 200 ms interval, with a 3.5 second listener wait. Live Android has its pre-existing 1-second foreground polling. Tests verify a second client receives the HTTP wakeup within 5 seconds under local conditions. **Do not claim WAN, background-OS wakeup, or native AnkiWeb scheduling convergence within 5 seconds**; those depend on third parties and real networks/devices.
- **#9, server dispatch:** `change_events` is a durable indexed SQLite log with collection, source device, target device and change kind; its global sequence commits in the same transaction as review inserts/enrichment, undo, confirmed native upload, settings, commands and skin import. Events are filtered server-side for destination devices and collections. A reconnecting device can query its earlier cursor and recover changes across process restarts. A bounded history logs 50,000 most recent changes, returning a reset indicator to older clients.
- **#10, suppress source-device echoes:** a review or native receipt from `phone` does not mark a `phone` watcher as changed, while all other relevant devices are informed; command notifications go only to the target device. The POST response still acknowledges the original event normally. Duplicate retries do not generate repeat notifications. The desktop watcher supplies its stable device and collection identifiers, advances past suppressed changes, and wakes its normal sync pipeline only on matching remote updates.

## Tests and evidence

`python -m pytest -q tests --ignore=tests/test_native_anki.py --maxfail=1`: **124 passed, 1 skipped** (the remaining skip is missing optional PySide6 in the Linux development runtime). `tests/test_native_anki.py` requires the externally installed Anki native package.

Added `tests/test_device_scoped_notifications.py` covering two live HTTP clients, cross-process cursor persistence, five-second local wakeup, origin exclusion, multi-collection isolation, targeted commands, global settings, auth, duplicate replay, and real packaged add-on acceptance.

**Do not merge or release until CI passes on the exact new SHA**, especially Windows real installed Anki startup plus Android/AnkiDroid 20→10→20 cross-device and full acceptance. The previous PR #9 baseline 11/11 green run is not a substitute for acceptance of modified code.

## External blockers

Google Cloud project/billing authorization, actual hosted HTTPS deployment and migration of the original Windows database/token/private skin, unknown original Android debug signer, and acceptance on the owner’s actual physical Windows and Android devices remain external. No private Eren artwork, credentials, Anki user collections or signing keys are included in this public source checkpoint.
