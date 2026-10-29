$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$python = if (Test-Path '.venv\Scripts\python.exe') { (Resolve-Path '.venv\Scripts\python.exe').Path } else { 'python' }
& $python -m desktop.app
if ($LASTEXITCODE -ne 0) { throw 'Desktop app exited with an error. Run scripts\setup_windows.ps1 first.' }
