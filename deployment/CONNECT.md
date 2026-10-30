# Connect the devices securely

1. Install the companion server on an always-on PC. The installer offers to start **AnkiCompanion Server** and an optional start-at-sign-in task. Otherwise open **AnkiCompanion Server** from Start. It binds only to `127.0.0.1:8765`; its private data is under `%LOCALAPPDATA%\AnkiCompanion\server` in packaged Windows builds.
2. Install Tailscale on the PC and Android phone and sign in to the same permitted network. Enable HTTPS when prompted by Tailscale Serve.
3. Run `deployment/connect-tailscale.ps1` on the PC. It configures a private HTTPS endpoint and verifies `/health`. No router port forwarding is required. Do not expose the unencrypted port to the Internet.
4. Enter the printed HTTPS address and the server's `token.txt` pairing token in **Connect** on both companion apps. Keep the token private. Both use the same collection ID, normally `primary`.
5. Install both Android packages: **AnkiCompanion** and **AnkiDroid Companion**. The latter is a separate edition of AnkiDroid with the implemented integration; stock AnkiDroid may remain installed. The ARM64 package is for modern ARM64 phones. In Anki desktop and **AnkiDroid Companion**, sign in to the same AnkiWeb account and complete the initial collection sync, choosing the correct upload/download direction. Automatic sync never guesses the direction of a full collection replacement.
6. Install `Anki_Companion_Bridge.ankiaddon` in Anki desktop (**Tools → Add-ons → Install from file**), restart Anki, and configure its `server_url`, `token`, and `collection_id`. Keep `auto_sync` enabled. The add-on uses Anki's native collection synchronization after answers and during active study, and reconciles review events separately with the companion server.
7. Import the existing private skin ZIP using **Skins → Import ZIP**, then select that skin. The public installer contains a neutral fallback; the complete private checkpoint retains the original personal pack unchanged. Existing daily choices remain fixed for that study day, and skin/goal changes take effect on the next new day.
8. In the phone companion, grant **Anki access** to the separate AnkiDroid Companion edition. Select the shared parent deck and save settings. The companion discovers its permission-protected API; it never assumes stock AnkiDroid supports the extension.
9. Tap **Live widget updates** once at the start of a study session. Its notification keeps five-second progress polling active, requests native collection refresh when needed, and retries offline work. AnkiDroid sends review-change wakeups after answers. Without a live session, Android schedules background work approximately every 15 minutes and may defer it; Android 15 may stop a data-sync session after six hours. The widget warning animation runs independently in the launcher.
10. Add the AnkiCompanion home-screen widget. On Windows, clicking X shows the compact dock; clicking Open restores the main window. Use **Study next subdeck** to sync and open the next eligible deck. A remote phone study command appears as a notification when Android prohibits a background activity launch; tapping it completes the handoff.

## Verification and updates

The shipped development packages have passed compilation, installer/server smoke checks, unit tests and the Android widget animation test. See `CHECKPOINT.md` for the current full cross-device acceptance result; a successful APK build alone is not proof that collections converge.

The HTTPS setup script is implemented and local TLS authentication/certificate tests pass. Your Tailscale account and physical PC/phone connection still require your sign-in and a device test. Keep the server PC awake and connected.

The apps discover approved GitHub Releases automatically and offer an Update button. Source commits alone are not installable updates. Production release signing keys must be configured and reused before publishing; see `UPDATES.md`. No production release has been published.

Primary references: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [AnkiDroid source](https://github.com/ankidroid/Anki-Android/tree/d9bf072f814a0c37d30a694192593b31ff2df875), [Anki sync server](https://docs.ankiweb.net/sync-server.html).
