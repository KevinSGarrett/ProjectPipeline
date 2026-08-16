[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param(
  [Parameter(Mandatory=$true)][string]$ProjectRoot,
  [Parameter(Mandatory=$true)][string]$WinSWPath
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path $ProjectRoot).Path
$source = (Resolve-Path $WinSWPath).Path
$target = Join-Path $root 'ProjectPipelineService.exe'
if ($PSCmdlet.ShouldProcess($target, 'Install verified WinSW service wrapper and Project Pipeline service')) {
  Copy-Item -LiteralPath $source -Destination $target -Force
  Copy-Item -LiteralPath (Join-Path $root 'infrastructure\windows\ProjectPipelineService.xml') -Destination (Join-Path $root 'ProjectPipelineService.xml') -Force
  & $target install
  & $target start
}
