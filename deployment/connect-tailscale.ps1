param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$tailscale = (Get-Command tailscale.exe -ErrorAction Stop).Source
$state = (& $tailscale status --json | ConvertFrom-Json)
if ($state.BackendState -ne 'Running') { throw 'Sign in to Tailscale on this PC and phone first.' }
& $tailscale serve --bg --https=443 "http://127.0.0.1:$Port"
if ($LASTEXITCODE -ne 0) { throw 'Tailscale Serve did not start. Follow its HTTPS enablement link, then rerun.' }
$name = $state.Self.DNSName.TrimEnd('.')
$url = "https://$name"
$health = Invoke-RestMethod "$url/health"
if ($health.status -ne 'ok') { throw 'Server is not healthy. Start AnkiCompanion Server first.' }
Write-Host "Verified server: $url"
Write-Host 'Use this URL on both devices. Enter the pairing token shown in the server data folder.'
Write-Host 'Keep this PC awake; both devices must be signed in to the same permitted Tailscale network.'
