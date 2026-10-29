$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
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
