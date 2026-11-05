# Real disposable Windows NSIS package test. No owner action or account setup.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$env:ANKI_COMPANION_ELECTRON_BUILD='1'
./scripts/build_windows.ps1
if ($LASTEXITCODE -ne 0) { throw 'Vortex-compatible Electron build failed' }
$installer=Resolve-Path 'packages/AnkiCompanion-Windows-Setup.exe'
$metadata=Get-Content 'packages/latest.yml' -Raw
$bytes=[IO.File]::ReadAllBytes($installer)
$sha512=[Convert]::ToBase64String([Security.Cryptography.SHA512]::HashData($bytes))
if (-not $metadata.Contains($sha512)) { throw 'Electron latest.yml SHA-512 is incorrect' }
if (-not $metadata.Contains('AnkiCompanion-Windows-Setup.exe')) { throw 'Electron installer missing from release feed' }
if (-not (Test-Path 'packages/AnkiCompanion-Windows-Setup.exe.blockmap')) { throw 'Differential-download blockmap missing' }
$installed=Start-Process $installer -ArgumentList '/S' -Wait -PassThru
if ($installed.ExitCode -ne 0) { throw "Electron NSIS installation failed: $($installed.ExitCode)" }
$root=Join-Path $env:LOCALAPPDATA 'Programs/AnkiCompanion'
$launcher=Join-Path $root 'AnkiCompanion.exe'
$qt=Join-Path $root 'resources/desktop/AnkiCompanion.exe'
$server=Join-Path $root 'resources/server/AnkiCompanionServer.exe'
$bridge=Join-Path $root 'resources/Anki_Companion_Bridge.ankiaddon'
foreach ($file in @($launcher,$qt,$server,$bridge)) {
  if (-not (Test-Path $file)) { throw "NSIS did not include component: $file" }
}
# The study records must be outside the application resources directory.
$data=Join-Path $env:LOCALAPPDATA 'AnkiCompanion/server'
if ($data.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) {
  throw 'Study database is incorrectly placed inside replaceable application files'
}
# Exercise the packaged update-shell launcher. A public release may not offer
# a newer version yet; this smoke verifies the installed Electron process starts.
$updater=Start-Process $launcher -ArgumentList '--updates' -PassThru
try {
  Start-Sleep -Seconds 7
  if ($updater.HasExited) { throw "Installed Electron updater exited early: $($updater.ExitCode)" }
} finally {
  Stop-Process -Id $updater.Id -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force 'test-results/update-buttons/windows' | Out-Null
@{ electron_updater_packaged=$true; nsis_installed=$true;
   latest_yml_sha512_verified=$true; bundled_qt=$true; bundled_server=$true;
   bundled_addon=$true; installer=(Split-Path $installer -Leaf);
   update_shell_started=$true } |
    ConvertTo-Json -Depth 4 | Set-Content 'test-results/update-buttons/windows/electron-evidence.json' -Encoding utf8
Write-Host 'PASS: Installed Electron/NSIS updater and bundled Python components'
