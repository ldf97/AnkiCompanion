# Connect Anki Companion

Set `server_url` and the server's pairing `token`, then restart Anki. Keep the same `collection_id` on all devices using the same synchronized Anki collection; this makes the same review count only once. Use a different collection ID for a different collection. `device_id` is generated once automatically.

The add-on sends review IDs, card IDs and answer durations; it does not upload card text. It queues events locally until the server acknowledges them. It also sends deck names/counts and polls study commands.

`auto_sync` asks Anki to sync while idle (at most once per minute), after study, and before a remote study command. It uses Anki's existing account/settings and may show Anki's own conflict/login dialogs. It does not replace AnkiWeb or silently resolve collection conflicts. AnkiDroid must still synchronize its collection too.

Review events are backfilled over the most recent 370 days in bounded pages. Review-log rescans detect recent undo operations. A deleted historical record outside the recent reconciliation window is not automatically retracted. Actual compatibility must be checked against your installed Anki version.
