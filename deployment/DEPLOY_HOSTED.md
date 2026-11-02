# Always-on AnkiCompanion server deployment

The user's Windows laptop (ASUS TUF Gaming A16 FA617NS) can be off while an always-on HTTPS host retains the coordination database, reviews, skins and per-device revision receipts. **Deploying this infrastructure requires a user-owned Linux host and DNS/domain. Neither GitHub nor this source repository supplies a free always-on host by itself.**

## One-time provisioning

Create a Linux x86-64/ARM64 VM with Docker Engine and Docker Compose installed. Allow public TCP 80, 443 and UDP 443. Point a DNS A/AAAA record to the host. Create a non-root `ankicompanion` SSH deploy user who can run `docker compose` (host operator's responsibility). On that host provision external Docker volume **`ankicompanion_data`** once. Do not delete or recreate this volume during updates: it contains server token, SQLite WAL/database, private skin imports, and server settings.

Configure GitHub environment `hosted-production` with protected secrets:

- `DEPLOY_HOST`: hostname or IP of the Linux host.
- `DEPLOY_USER`: SSH username on host.
- `DEPLOY_SSH_KEY`: deploy-only private SSH key; DO NOT commit.
- `DEPLOY_KNOWN_HOSTS`: pinned SSH host-key fingerprint line (known_hosts format), not `StrictHostKeyChecking=no`.
- `COMPANION_DOMAIN`: DNS hostname serving HTTPS, not a `trycloudflare.com` ephemeral address.
- `ACME_EMAIL`: TLS certificate contact address.

`deploy-hosted.yml` uploads the exact source revision and uses `docker compose up -d --build --wait` on that host. A persistent Caddy data volume retains certificates and automatically renews them. **The workflow will not claim a deployment if the secrets, host or DNS are missing.**

### Migration from the Windows-hosted database

A new cloud server starts with a NEW token, without the old Windows events/skins. Copying the exact existing SQLite database, WAL and `packs` data, plus `token.txt`, into the cloud `/data` volume **before allowing clients to connect** is necessary to maintain the same progress and credentials. Use a consistent SQLite snapshot with the Windows server stopped; never overwrite a live database. There is deliberately no automatic destructive data migration or fabricated server URL.

After migration, use the app's Connection/Pairing UI to point clients to `https://COMPANION_DOMAIN` with the existing token; no collection or review records should be deleted. A later enhancement can propagate server endpoint changes through existing authenticated peers.

### Release, acceptance and recovery

The GitHub deployment job checks `/health` over public HTTPS and verifies unauthenticated `/v1/state` is rejected. It cannot validate private event history without a server token. Database volume persists across container replacements/reboots and `docker compose down` (not an operator deleting the external volume). No remote passwords or private signing keys are stored in git.

Cloud hosting costs, DNS/domain ownership, host hardening and uptime remain the host owner's responsibility. Offline devices see the committed revisions when they reconnect, but native Anki collection sync additionally depends on AnkiWeb availability.
