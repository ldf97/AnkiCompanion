$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv; if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed.' } }
$python = (Resolve-Path '.venv\Scripts\python.exe').Path
& $python -m pip install -r requirements-server.txt -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Setup complete. In separate PowerShell windows run scripts\start_server.ps1 and scripts\start_desktop.ps1.'
Write-Host 'Local server is bound to 127.0.0.1 only. Remote devices require secure network configuration.'
