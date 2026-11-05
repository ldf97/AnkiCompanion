$ErrorActionPreference = 'Stop'
$root = Split-Path $MyInvocation.MyCommand.Path -Parent
$out = Join-Path $root 'dist\AnkiCompanion-Recovery.exe'
New-Item -ItemType Directory -Force (Split-Path $out -Parent) | Out-Null
$src = Get-Content (Join-Path $root 'AnkiCompanionRecovery.cs') -Raw
Add-Type -TypeDefinition $src -ReferencedAssemblies @('System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll') -OutputAssembly $out -OutputType WindowsApplication
if (!(Test-Path $out)) { throw 'Recovery binary was not produced' }
Write-Host "Built stand-alone AnkiCompanion Recovery: $out"
