[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = 'Stop'
$root=(Resolve-Path $ProjectRoot).Path
$service=Join-Path $root 'ProjectPipelineService.exe'
if (-not (Test-Path $service)) { throw 'ProjectPipelineService.exe is not installed in the supplied project root.' }
if ($PSCmdlet.ShouldProcess($service, 'Stop and uninstall Project Pipeline service')) {
  & $service stop
  & $service uninstall
}
