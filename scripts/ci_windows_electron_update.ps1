# Real disposable Windows NSIS package test. No owner action or account setup.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$env:ANKI_COMPANION_ELECTRON_BUILD='1'
# TEST ONLY: Modify the disposable runner workspace, never committed Electron
# runtime, to point the baseline at a local release feed and click its actual
# updater API automatically. The target installer is built from restored source.
$originalElectron=Get-Content 'updater/main.js' -Raw
$injection=@'
if (process.env.ANKI_COMPANION_CI_UPGRADE === "1") {
  app.whenReady().then(() => {
    autoUpdater.setFeedURL({provider:"generic",url:"http://127.0.0.1:8767/"});
    autoUpdater.on("update-available", () => setImmediate(() => downloadUpdate()));
    autoUpdater.on("update-downloaded", () => setImmediate(() => installUpdate()));
  });
}
'@
$needle='const single = app.requestSingleInstanceLock();'
if (-not $originalElectron.Contains($needle)) { throw 'Missing Electron CI fixture anchor' }
Set-Content 'updater/main.js' ($originalElectron.Replace($needle,$injection+"`n"+$needle)) -Encoding utf8
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
# Electron's per-user NSIS target determines its own install directory.
# Discover the real installed launcher instead of assuming Inno's old path.
$programs=Join-Path $env:LOCALAPPDATA 'Programs'
$launcher=$null
for ($attempt=0; $attempt -lt 40 -and -not $launcher; $attempt++) {
  $matches=@(Get-ChildItem $programs -Filter AnkiCompanion.exe -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '[\\/]resources[\\/]' })
  if ($matches.Count -gt 0) { $launcher=$matches[0].FullName; break }
  Start-Sleep -Seconds 1
}
if (-not $launcher) {
  Write-Host 'NSIS per-user program directories:'
  Get-ChildItem $programs -Directory -ErrorAction SilentlyContinue | Select-Object FullName | Format-Table
  throw 'NSIS installer returned success but did not create a launcher'
}
$root=Split-Path $launcher -Parent
Write-Host "Verified NSIS installed at $root"
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

# TEST ONLY: create a genuine newer installer, metadata and local GitHub-like
# release feed. Do not put a mock provider or test auto-click in production.
Set-Content 'updater/main.js' $originalElectron -Encoding utf8
$version=Get-Content 'VERSION.json' -Raw | ConvertFrom-Json
if ($version.version -ne '0.1.1') { throw 'Two-version test expects baseline 0.1.1' }
$version.version='0.1.2'
$version.build=3
$version.commit='ci-installed-nsis-upgrade'
$version | ConvertTo-Json -Depth 8 | Set-Content 'VERSION.json' -Encoding utf8
$qtOriginal=Get-Content 'desktop/app.py' -Raw
$before="self.update_status=QLabel('Updates handled by Windows updater')"
if (-not $qtOriginal.Contains($before)) { throw 'Missing Qt source patch anchor' }
Set-Content 'desktop/app.py' ($qtOriginal.Replace($before,
  "self.update_status=QLabel('PATCH CONFIRMED · Windows updater')")) -Encoding utf8
./scripts/build_windows.ps1
if ($LASTEXITCODE -ne 0) { throw 'Could not build real target version 0.1.2' }
if (-not (Test-Path 'packages/latest.yml')) { throw 'Target feed metadata missing' }
$serverlog=Join-Path (Get-Location) 'test-results/update-buttons/windows/http-server.log'
$feed=Start-Process python -ArgumentList '-m','http.server','8767','--bind','127.0.0.1',
  '--directory',(Resolve-Path 'packages').Path -PassThru -RedirectStandardOutput $serverlog
try {
  $ready=$false
  for($i=0;$i -lt 30;$i++){
    try{
      $meta=Invoke-WebRequest -Uri 'http://127.0.0.1:8767/latest.yml' -UseBasicParsing -TimeoutSec 3
      if($meta.StatusCode -eq 200){$ready=$true;break}
    }catch{}
    Start-Sleep -Seconds 1
  }
  if(-not $ready){throw 'Local GitHub-like NSIS test feed did not start'}
  $env:ANKI_COMPANION_CI_UPGRADE='1'
  $upgrade=Start-Process $launcher -ArgumentList '--updates' -PassThru
  $newVersion=$false
  $registry='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
  for($i=0;$i -lt 180;$i++) {
    foreach($entry in @(Get-ChildItem $registry -ErrorAction SilentlyContinue)) {
      $v=Get-ItemProperty $entry.PSPath -ErrorAction SilentlyContinue
      if($v.DisplayName -eq 'AnkiCompanion' -and $v.DisplayVersion -eq '0.1.2'){
        $newVersion=$true
        break
      }
    }
    if($newVersion){break}
    Start-Sleep -Seconds 1
  }
  if(-not $newVersion){throw 'Electron updater did not apply NSIS v0.1.2 over v0.1.1'}
  Write-Host 'PASS: Electron updater downloaded latest.yml and installed real NSIS v0.1.2 over v0.1.1'
  @{v1='0.1.1';v2='0.1.2';actual_nsis_in_place_upgrade=$true;
    via_electron_updater=$true;no_reinstall=$true} |
    ConvertTo-Json | Set-Content 'test-results/update-buttons/windows/in-place-update.json' -Encoding utf8
} finally {
  Remove-Item Env:ANKI_COMPANION_CI_UPGRADE -ErrorAction SilentlyContinue
  Stop-Process -Id $feed.Id -ErrorAction SilentlyContinue
}

