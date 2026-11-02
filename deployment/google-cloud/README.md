# Google Compute Engine option for AnkiCompanion

**Recommended over Railway for this project's existing SQLite architecture.** It uses native POSIX persistent disks; it does not put a live SQLite database on Google Drive or Cloud Storage FUSE. Select this instead of Railway in the provider setup. Google Cloud signup and billing are independent of the Google Drive/Gmail connectors.

## Provisioning, once, with cloud web UIs

Open https://console.cloud.google.com and create a billing-enabled project. Enable Compute Engine, IAM and Cloud Storage APIs. Create a **private, versioned Google Cloud Storage bucket for Terraform state only**, never for the running SQLite file. Establish a GitHub Workload Identity Federation provider restricted to the AnkiCompanion repository and main branch, and a deployment service account with the minimum roles necessary to manage Compute Engine instances, disks, VPC/firewall, service accounts and the Terraform state bucket.

In GitHub repository Settings → Environments, create protected environment \`google-cloud-production\`. Configure secrets \`GCP_PROJECT_ID\`, \`GCP_ACME_EMAIL\`, \`GCP_TF_STATE_BUCKET\`, \`GCP_WIF_PROVIDER\`, \`GCP_DEPLOY_SERVICE_ACCOUNT\`, and optionally \`GCP_DOMAIN\`. Require approval of deployments. All secrets stay out of git.

On a **tested main branch commit**, select Actions → Google Cloud AnkiCompanion → Run workflow. First use \`apply=false\` to review the plan. Then use \`apply=true\` to provision. No end-user PowerShell is involved. Backend state is in the GCS bucket, so repeat runs update the same VM and disks instead of recreating an unrelated host. The source checkout on the VM is pinned to the exact Git SHA.

The plan creates a single standard \`e2-micro\` in \`us-east1\`, 10 GB boot + 15 GB persistent data disk + 5 GB persistent backups disk, daily GCE data-disk snapshots, automatic VM restarts, and private port 8765 behind Caddy's public HTTPS. SSH is permitted only via Google IAP. The two persistent disks have Terraform \`prevent_destroy = true\`; the startup script checks existing filesystems, never reformats an existing volume, and validates Docker volume locations before updating.

A public static IPv4 address is reserved (potential **billable** charge) for stable phone pairing. If \`GCP_DOMAIN\` is unset, the app uses an \`*.sslip.io\` hostname reflecting that address and Caddy provisions TLS; this uses a third-party DNS provider and may not be ideal for long-term production. A domain you own provides more control.

## One-time migration, entirely with graphical interfaces

This is necessary **once** because the existing Windows server already holds your study history, settings, Eren/private skin imports, and original pairing token. It is not part of future updates.

1. Open **AnkiCompanion** on Windows and click **Export to Google Cloud**. Save the file with its suggested name, **AnkiCompanion-Server-Migration.zip**. The export uses SQLite's online backup API to capture WAL-committed reviews, includes the exact original token and private skin assets, and verifies the archive before saving. It does not shut down or alter the original server. The ZIP is **not encrypted**; keep it private.
2. In **Google Cloud Console → Compute Engine → VM instances**, click **SSH** for the new AnkiCompanion VM. In the SSH-in-browser window, choose **Upload File** and select that ZIP. It must be uploaded with the exact suggested filename into the VM account's home folder. Do not upload it to GitHub.
3. Return to the VM instances page and **Restart/Reset** the VM. The pinned startup script automatically finds the uploaded ZIP, validates every SHA-256 hash, checks the SQLite database and pairing token, refuses to overwrite any existing hosted server, restores the original state, and deletes the uploaded ZIP after success.
4. Confirm HTTPS health and that unauthenticated state requests return 401. Open **Connection** on Windows and Android and select the new hosted HTTPS URL with the **same original token**. The Windows application now remembers the hosted connection across restarts and provides a hosted **Pair phone** link. Confirm the same progress and skin catalog are present before retiring the Windows-hosted server.

After successful verification, delete the remaining migration ZIP from your Windows Downloads folder. The original Anki collection, local server database, and installed personal skin are never uninstalled or overwritten by this migration.

If the VM has no existing database and you have not uploaded the ZIP, it intentionally stays in **MIGRATION_REQUIRED** state instead of inventing an empty new profile. On an error the original Windows data stays untouched, and the importer refuses destructive overwrites. No PowerShell or command-line tools are required from the user.

## Important limitations and expenses

Google's Compute Engine Always Free program covers eligible use of an \`e2-micro\` in \`us-east1\`, \`us-west1\` or \`us-central1\` and up to 30 GB-months of standard persistent disk. **Public IPv4 addresses, disk snapshots, excess traffic and Google Cloud Storage can cost money.** Set a budget before provisioning.

Google cloud projects or billing authorization cannot be created via a Google Drive/Gmail connection. The migration is a one-time prerequisite, not part of normal updates. A Google Cloud VM cannot fix an already-installed Android APK signed by an incompatible certificate; that is an independent Android package-manager constraint. Real phone/laptop upgrade acceptance must be performed before promising lossless updates.
