# Google Compute Engine option for AnkiCompanion

**Recommended over Railway for this project's existing SQLite architecture.** It uses native POSIX persistent disks; it does not put a live SQLite database on Google Drive or Cloud Storage FUSE. Select this instead of Railway in the provider setup. Google Cloud signup and billing are independent of the Google Drive/Gmail connectors.

## Provisioning, once, with cloud web UIs

Open https://console.cloud.google.com and create a billing-enabled project. Enable Compute Engine, IAM and Cloud Storage APIs. Create a **private, versioned Google Cloud Storage bucket for Terraform state only**, never for the running SQLite file. Establish a GitHub Workload Identity Federation provider restricted to the AnkiCompanion repository and main branch, and a deployment service account with the minimum roles necessary to manage Compute Engine instances, disks, VPC/firewall, service accounts and the Terraform state bucket.

In GitHub repository Settings → Environments, create protected environment \`google-cloud-production\`. Configure secrets \`GCP_PROJECT_ID\`, \`GCP_ACME_EMAIL\`, \`GCP_TF_STATE_BUCKET\`, \`GCP_WIF_PROVIDER\`, \`GCP_DEPLOY_SERVICE_ACCOUNT\`, and optionally \`GCP_DOMAIN\`. Require approval of deployments. All secrets stay out of git.

On a **tested main branch commit**, select Actions → Google Cloud AnkiCompanion → Run workflow. First use \`apply=false\` to review the plan. Then use \`apply=true\` to provision. No end-user PowerShell is involved. Backend state is in the GCS bucket, so repeat runs update the same VM and disks instead of recreating an unrelated host. The source checkout on the VM is pinned to the exact Git SHA.

The plan creates a single standard \`e2-micro\` in \`us-east1\`, 10 GB boot + 15 GB persistent data disk + 5 GB persistent backups disk, daily GCE data-disk snapshots, automatic VM restarts, and private port 8765 behind Caddy's public HTTPS. SSH is permitted only via Google IAP. The two persistent disks have Terraform \`prevent_destroy = true\`; the startup script checks existing filesystems, never reformats an existing volume, and validates Docker volume locations before updating.

A public static IPv4 address is reserved (potential **billable** charge) for stable phone pairing. If \`GCP_DOMAIN\` is unset, the app uses an \`*.sslip.io\` hostname reflecting that address and Caddy provisions TLS; this uses a third-party DNS provider and may not be ideal for long-term production. A domain you own provides more control.

## One-time original-server migration

**On first provision the VM will not start a blank server.** To protect the already existing history/settings/token/private artwork, the previous Windows server's SQLite database must be consistently backed up (SQLite online backup/WAL included), then transferred **once** to the persistent data disk with the original \`token.txt\` and \`packs/\` files. Do not copy only the live \`.sqlite3\` file. Never upload this material to public GitHub. A new blank cloud token would disconnect the existing phone and lose centralized progress.

After the migration, reboot the VM via Google Cloud Console, verify \`https://HOST/health\` and a 401 rejection for \`https://HOST/v1/state\`, and use **Connection** in Windows/Android to select the hosted endpoint. Normal code updates thereafter require **no restores**: app settings, SQLite, pairing token and skin packs remain on protected disks.

## Important limitations and expenses

Google's Compute Engine Always Free program covers eligible use of an \`e2-micro\` in \`us-east1\`, \`us-west1\` or \`us-central1\` and up to 30 GB-months of standard persistent disk. **Public IPv4 addresses, disk snapshots, excess traffic and Google Cloud Storage can cost money.** Set a budget before provisioning.

Google cloud projects or billing authorization cannot be created via a Google Drive/Gmail connection. The migration is a one-time prerequisite, not part of normal updates. A Google Cloud VM cannot fix an already-installed Android APK signed by an incompatible certificate; that is an independent Android package-manager constraint. Real phone/laptop upgrade acceptance must be performed before promising lossless updates.
