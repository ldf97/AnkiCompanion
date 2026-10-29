# Update channel

The server checks `ldf97/AnkiCompanion` stable GitHub Releases. Each release must have `update.json`, an exact source commit, a numeric version/build, filenames, byte lengths and SHA-256 hashes. Android checks hourly during successful background/foreground refresh; desktop checks on launch and every 15 minutes. Both expose an Update button. Offline or sleeping devices catch up when the OS next permits network work; continuous background delivery is not guaranteed by Android.

Downloads reject redirects outside the approved GitHub asset hosts and strip the API credential when changing host. Clients authenticate to the companion server. Android checks package ID, increasing version code and the installed signing certificate before asking the OS to install. Windows checks Authenticode trust plus the publisher thumbprint embedded at build time before executing the installer. A development build without a publisher pin cannot silently install an update.

`release-candidate.yml` builds signed candidates only when manually started on main. Configure the `signing` environment with a persistent Android keystore and a trusted Windows code-signing certificate. Required secrets are named in that workflow. Keep private key backups outside the repository. Never replace the key between releases. The workflow fails if signing material is absent and **does not publish a release**. It has not been run with production credentials in this workspace.

After physical-device acceptance and explicit owner authorization, publish the exact candidate assets plus `update.json` in a stable GitHub Release tagged `vVERSION`. The app updater then detects that release. Changing code on main by itself is not an installable update.

CI development artifacts are unsigned on Windows and debug-signed on Android. GitHub runner debug keys may differ between runs and from the previously supplied APK. Do not uninstall an existing app just to bypass a signature mismatch: preserve its data/settings and use the original signing key or a planned migration. Production in-place update installation remains unverified until the persistent keys and actual devices are available.
