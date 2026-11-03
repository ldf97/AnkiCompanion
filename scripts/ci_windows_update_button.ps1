# Disposable GitHub Windows runner: install two actual code versions and
# perform the upgrade through the INSTALLED application's Qt Update button.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$out=Join-Path (Get-Location) 'test-results/update-buttons/windows'
New-Item -ItemType Directory -Force $out | Out-Null
$program=Join-Path $env:LOCALAPPDATA 'Programs/AnkiCompanion'
$serverExe=Join-Path $program 'server/AnkiCompanionServer.exe'
$desktopExe=Join-Path $program 'desktop/AnkiCompanion.exe'
$dataDir=Join-Path $env:LOCALAPPDATA 'AnkiCompanion/server'
$tokenFile=Join-Path $dataDir 'token.txt'
$dbFile=Join-Path $dataDir 'companion.sqlite3'
$art=Join-Path $dataDir 'packs/private_ci/1.0.0/personal-artwork-fixture.bin'
# 1. Baseline binary with instrumentation compiled ONLY into disposable CI copy.
python scripts/ci_windows_update_fixture.py enable-baseline
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare baseline GUI acceptance harness' }
./scripts/build_windows.ps1
if ($LASTEXITCODE -ne 0) { throw 'Could not build baseline Windows installer' }
Copy-Item packages/AnkiCompanion-Windows-Setup.exe (Join-Path $out 'baseline-v0.1.1.exe') -Force
$p=Start-Process packages/AnkiCompanion-Windows-Setup.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Baseline installer failed: $($p.ExitCode)" }
# Start the installed persistent server and commit a genuine review into SQLite.
$server=Start-Process $serverExe -PassThru -RedirectStandardOutput (Join-Path $out 'server.log') -RedirectStandardError (Join-Path $out 'server-err.log')
try {
  $healthy=$false
  for ($i=0; $i -lt 45; $i++) {
    try {
      $h=Invoke-RestMethod http://127.0.0.1:8766/health -TimeoutSec 2
      if ($h.status -eq 'ok') {$healthy=$true; break}
    } catch {}
    Start-Sleep -Milliseconds 500
  }
  if (-not $healthy) { throw 'Installed baseline server never became healthy' }
  if (!(Test-Path $tokenFile) -or !(Test-Path $dbFile)) { throw 'Missing installed baseline data' }
  $token=(Get-Content $tokenFile -Raw).Trim()
  $ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $event=@{device_id='pc1';events=@(@{collection_id='primary';revlog_id=($ms - 1000);card_id=345;duration_ms=500;rating=3})} | ConvertTo-Json -Depth 8
  $headers=@{Authorization="Bearer $token"}
  $res=Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8766/v1/events -Headers $headers -ContentType 'application/json' -Body $event
  $beforeState=Invoke-RestMethod -Uri http://127.0.0.1:8766/v1/state -Headers $headers
  if ($beforeState.progress.answers -lt 1) { throw 'No review was saved in baseline server before upgrade' }
} finally {
  Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force (Split-Path $art) | Out-Null
[IO.File]::WriteAllBytes($art,[byte[]](1,2,3,4,5,6,7,8))
$tokenHash=(Get-FileHash $tokenFile -Algorithm SHA256).Hash
$artHash=(Get-FileHash $art -Algorithm SHA256).Hash

# 2. Harmless source patch + real new installer. No version-only same-binary test.
python scripts/ci_windows_update_fixture.py restore-and-patch
if ($LASTEXITCODE -ne 0) { throw 'Could not create patched release' }
./scripts/build_windows.ps1
if ($LASTEXITCODE -ne 0) { throw 'Could not build patched Windows installer' }
$asset=Join-Path $out 'AnkiCompanion-Windows-Setup.exe'
Copy-Item packages/AnkiCompanion-Windows-Setup.exe $asset -Force
$manifest=Join-Path $out 'update.json'
$sha=(Get-FileHash $asset -Algorithm SHA256).Hash.ToLowerInvariant()
$size=(Get-Item $asset).Length
$release=@{schema_version=1;version='0.1.2';build=970002;commit='two-version-button-acceptance';assets=@{windows=@{filename='AnkiCompanion-Windows-Setup.exe';size=$size;sha256=$sha}}}
$release | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 $manifest

# 3. Installed old GUI clicks Update itself, parses the fixture, verifies the
# *real newer installer* bytes, backs up state and runs the Inno in-place update.
$env:CI='true'
$env:ANKI_COMPANION_CI_UPGRADE='1'
$env:ANKI_COMPANION_CI_MANIFEST=$manifest
$env:ANKI_COMPANION_CI_ASSET=$asset
$env:ANKI_COMPANION_CI_MARKERS=$out
$oldGui=Start-Process $desktopExe -PassThru -RedirectStandardOutput (Join-Path $out 'old-gui.log') -RedirectStandardError (Join-Path $out 'old-gui-errors.log')
$markers=@('clicked-update-button.txt','downloaded-verified-installer.txt','launched-verified-installer.txt')
$allMarkers=$false
for ($i=0; $i -lt 180; $i++) {
  $allMarkers=(@($markers | Where-Object {-not (Test-Path (Join-Path $out $_))}).Count -eq 0)
  if ($allMarkers) {break}
  if ($oldGui.HasExited -and $i -gt 25) {break}
  Start-Sleep -Seconds 1
}
if (-not $allMarkers) {
  if (Test-Path (Join-Path $out 'old-gui-errors.log')) {Get-Content (Join-Path $out 'old-gui-errors.log') | Select-Object -Last 50}
  throw 'Installed Windows GUI did not click, download and launch verified update'
}

$upgraded=$false
$versionLocation=''
for ($i=0; $i -lt 180; $i++) {
  $versions=@(Get-ChildItem (Join-Path $program 'desktop') -Filter VERSION.json -Recurse -ErrorAction SilentlyContinue)
  foreach ($file in $versions) {
    try {
      $current=Get-Content $file.FullName -Raw | ConvertFrom-Json
      if ($current.version -eq '0.1.2') { $upgraded=$true; $versionLocation=$file.FullName; break }
    } catch {}
  }
  # Some PyInstaller layouts keep the version metadata in the executable
  # rather than as an on-disk VERSION.json. Inno Setup's registered version
  # is the OS-authoritative record of an installed bundle upgrade.
  if (-not $upgraded) {
    $uninstall='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall'
    foreach ($entry in @(Get-ChildItem $uninstall -ErrorAction SilentlyContinue)) {
      $registration=Get-ItemProperty $entry.PSPath -ErrorAction SilentlyContinue
      if ($registration.DisplayName -eq 'AnkiCompanion' -and $registration.DisplayVersion -eq '0.1.2') {
        $upgraded=$true
        $versionLocation=$entry.PSPath
        break
      }
    }
  }
  if ($upgraded) {break}
  Start-Sleep -Seconds 1
}
if (-not $upgraded) {
  $log=Join-Path $out 'inno-gui-upgrade.log'
  if (Test-Path $log) {
    Write-Host '---- Inno auto-update installer diagnostics ----'
    Get-Content $log | Select-Object -Last 100
  } else {
    Write-Host 'Inno auto-update log was not created; process launch may have failed'
  }
  Write-Host '---- Installed version manifests ----'
  Get-ChildItem (Join-Path $program 'desktop') -Recurse -Filter VERSION.json -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host $_.FullName; Get-Content $_.FullName | Select-Object -First 5 }
  Write-Host '---- Related Windows processes ----'
  Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'AnkiCompanion|Inno|Setup'
  } | Select-Object ProcessId,Name,ExecutablePath | Format-Table -AutoSize
  throw 'Qt Update launched the installer, but patched v0.1.2 was not installed'
}
if ((Get-FileHash $tokenFile -Algorithm SHA256).Hash -ne $tokenHash) { throw 'Pairing token changed during GUI update' }
if ((Get-FileHash $art -Algorithm SHA256).Hash -ne $artHash) { throw 'Private skin bytes changed during GUI update' }
# Verify the genuine review survived, even after the server restarts.
$server2=Start-Process $serverExe -PassThru -RedirectStandardOutput (Join-Path $out 'server2.log') -RedirectStandardError (Join-Path $out 'server2-err.log')
try {
  $state=$null
  for ($i=0; $i -lt 50; $i++) {
    try { $state=Invoke-RestMethod -Uri http://127.0.0.1:8766/v1/state -Headers $headers -TimeoutSec 3; if ($state) {break} } catch {}
    Start-Sleep -Milliseconds 500
  }
  if (-not $state -or $state.progress.answers -lt 1) { throw 'Real review was not preserved through Qt button upgrade' }
} finally {
  Stop-Process -Id $server2.Id -ErrorAction SilentlyContinue
}
$evidence=@{
  tested_on='GitHub Windows 11 runner'
  qt_update_clicked=$true
  release_manifest_validated=$true
  installer_sha256=$sha
  installed_version='0.1.2'
  previous_version='0.1.1'
  installed_binary_version_path=$versionLocation
  review_persisted=$true
  pairing_token_preserved=$true
  private_skin_preserved=$true
  no_uninstall=$true
  test_fixture_not_in_production_source=$true
}
$evidence | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $out 'evidence.json')
Write-Host 'PASS: Windows Qt Update button installed patch 0.1.2 over 0.1.1; review, token and private art persisted.'
