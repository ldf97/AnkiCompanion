# Run from any directory: powershell -ExecutionPolicy Bypass -File scripts\start_server.ps1
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$python = if (Test-Path '.venv\Scripts\python.exe') { (Resolve-Path '.venv\Scripts\python.exe').Path } else { 'python' }
if (-not $env:ANKI_COMPANION_DATA) { $env:ANKI_COMPANION_DATA = Join-Path $root 'data' }
Write-Host "Starting local Anki Companion server on http://127.0.0.1:8765"
& $python -m server.main --host 127.0.0.1 --port 8765
if ($LASTEXITCODE -ne 0) { throw 'Server exited with an error. Run scripts\setup_windows.ps1 first.' }
