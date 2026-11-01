$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
# Include the verified HTTPS pairing helper inside every update installer.
# Users never download or run this tool themselves.
$cloudflared = Join-Path $PSScriptRoot '..\deployment\cloudflared.exe'
$cloudflaredHash = '547057326266f0e1c7d50d102dbd22ff283d740c055bd61e94f10e2c606f89af'
if (!(Test-Path $cloudflared) -or (Get-FileHash -Path $cloudflared -Algorithm SHA256).Hash.ToLowerInvariant() -ne $cloudflaredHash) {
    $part = "$cloudflared.partial"
    try {
        Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/download/2026.9.0/cloudflared-windows-amd64.exe' -OutFile $part -TimeoutSec 120
        if ((Get-FileHash -Path $part -Algorithm SHA256).Hash.ToLowerInvariant() -ne $cloudflaredHash) { throw 'Unexpected cloudflared binary checksum' }
        Move-Item -LiteralPath $part -Destination $cloudflared -Force
    } finally { Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue }
}
python scripts/package_addon.py
if ($LASTEXITCODE -ne 0) { throw 'Add-on packaging failed' }
$common = @('--noconfirm','--clean','--paths','.', '--add-data','fonts;fonts','--add-data','assets;assets','--add-data','skins/study_companion;skins/study_companion','--add-data','VERSION.json;.', '--exclude-module','PyQt6','--exclude-module','PyQt5','--collect-all','resvg_py')
python -m PyInstaller @common --name AnkiCompanion --windowed installer/desktop_entry.py
if ($LASTEXITCODE -ne 0) { throw 'Desktop packaging failed' }
python -m PyInstaller @common --name AnkiCompanionServer --collect-all uvicorn installer/server_entry.py
if ($LASTEXITCODE -ne 0) { throw 'Server packaging failed' }
$compiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $compiler)) { throw 'Install Inno Setup 6 before building the installer.' }
$version=(Get-Content VERSION.json | ConvertFrom-Json).version
& $compiler "/DAppVersion=$version" installer/AnkiCompanion.iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
