# Always-on Railway deployment (#18)

This is an alternative to the self-managed VPS Docker/Caddy deployment.
The source is `.railway/railway.ts`, using Railway's current Infrastructure-as-Code format. The older `railway.json` config-as-code workflow was deprecated for new services in late 2026.

**Prerequisites for a real deployment:** connect a Railway hosting account, approve a long-running server and two persistent volumes, and create a public HTTPS Railway domain. Railway incurs hosting/storage charges. This repo and GitHub Actions are not themselves an always-on cloud host.

## What the infrastructure definition creates

- One long-running FastAPI service built using `server/Dockerfile`; one replica, because multiple independent SQLite replicas would corrupt or diverge the progress state.
- Virginia `/data` persistent volume (SQLite/WAL, pairing token, server settings, private skins).
- Separate Virginia `/backups` persistent volume. A verified snapshot is made **at the container's startup**, before the server opens/migrates its existing SQLite schema. If this snapshot fails, the new container does **not** start. The original database is not overwritten. On a brand-new empty volume, the server initializes without a snapshot.
- TLS is provided by Railway's HTTPS edge. Public `/health` returns 200; authenticated `/v1/state` rejects unauthorized requests. The service listens on fixed `PORT=8765`.

**Do not connect your phones to a blank newly created server.** First migrate the original Windows server's SQLite database, current token, and private `packs` into the mounted `/data` volume. A clean Railway project with a fresh token is not an upgrade of the existing installation. The server keeps these files through code/container changes, but initial Windows-to-cloud migration still requires a one-time user-approved transfer.

When deploying updates, do not select 'Delete volume', detach volumes, change their names, or decrease storage sizes. Validate a newly deployed HTTPS URL before changing the saved Connection on Windows/Android. The Windows companion now preserves remote endpoints and generates remote pairing links without starting a local relay.

Railway maintains server processes while the laptop is off, subject to plan availability and provider uptime. Disable serverless/app sleep for an always-on deployment. Use provider-managed volume snapshots/off-host backups in addition to the app's /backups volume. Normal code updates need **no manual restore**.

Helpful references:
- https://docs.railway.com/infrastructure-as-code/reference
- https://docs.railway.com/volumes
- https://docs.railway.com/deployments/healthchecks
