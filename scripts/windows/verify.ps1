[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference='Stop'
$root=(Resolve-Path $ProjectRoot).Path
$env:PYTHONPATH=Join-Path $root 'src'
& (Join-Path $root 'venv\Scripts\python.exe') (Join-Path $root 'scripts\run_command_center_service.py') --root $root --check
if ($LASTEXITCODE -ne 0) { throw 'Command Center service source-runtime check failed.' }
