# Connect the devices securely

1. Install the companion server on an always-on PC. Run **AnkiCompanion Server**. It binds only to `127.0.0.1:8765`; its private data is under `%LOCALAPPDATA%\AnkiCompanion\server` in packaged Windows builds.
2. Install Tailscale on the PC and Android phone and sign in to the same permitted network. Enable HTTPS when prompted by Tailscale Serve.
3. Run `deployment/connect-tailscale.ps1` on the PC. It configures a private HTTPS endpoint and verifies `/health`. No router port forwarding is required. Do not expose the unencrypted port to the Internet.
4. Enter the printed HTTPS address and the server's `token.txt` pairing token in **Connect** on both companion apps. Keep the token private. Both use the same collection ID, normally `primary`.
5. In Anki and AnkiDroid, configure the **same AnkiWeb account**, then finish their initial collection synchronization. AnkiWeb synchronizes scheduling and review logs; the companion server does not replace it. Keep Anki desktop and its configured add-on running. Enable AnkiDroid's built-in automatic sync on open/close.
6. Import the existing private skin ZIP using **Skins → Import ZIP**. The public installer contains only the neutral fallback. The private continuation retains the original personal pack unchanged.
7. Grant Anki access in the phone companion. **Live widget updates** starts an explicit study-session notification and polls the companion server every five seconds. Without it, background refresh is best-effort (normally 15 minutes, possibly delayed by Android). Android 15 may stop a data-sync session after six hours. The warning animation itself runs in the launcher and does not require this service.

## Current limits

Stock AnkiDroid exposes decks and a foreground `DO_SYNC` intent, but no complete review-history feed or sync-completion callback. **Sync AnkiDroid** invokes that supported intent. The experimental custom provider is disabled by default. The phone's review totals reach the companion through the desktop add-on after native collection synchronization. Automatic handoff while the reviewer stays open is **not verified or guaranteed**. Do not rely on the companion progress display to prove scheduling is synchronized.

The HTTPS setup script is implemented, but this workspace cannot sign into your Tailscale account or verify your actual PC/phone route. A local TLS integration test checks authentication and certificate enforcement, not your network. Perform `CROSS_DEVICE_SYNC_ACCEPTANCE.md` on the devices before treating the application as ready.

Primary references: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [AnkiDroid manual](https://docs.ankidroid.org/manual.html), [Anki sync server](https://docs.ankiweb.net/sync-server.html).
