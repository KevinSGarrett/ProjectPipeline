[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param([Parameter(Mandatory=$true)][string]$ProjectRoot,[Parameter(Mandatory=$true)][string]$CandidateArchive,[Parameter(Mandatory=$true)][string]$BackupDirectory)
$ErrorActionPreference='Stop'
$root=(Resolve-Path $ProjectRoot).Path
$archive=(Resolve-Path $CandidateArchive).Path
New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$backup=Join-Path $BackupDirectory "project-pipeline-pre-upgrade-$stamp.zip"
if ($PSCmdlet.ShouldProcess($root, 'Create pre-upgrade backup and stage candidate; production promotion remains separately gated')) {
  Compress-Archive -Path (Join-Path $root '*') -DestinationPath $backup -Force
  Write-Output "Backup created: $backup"
  Write-Output "Candidate staged for independent certification: $archive"
  Write-Output 'No automatic promotion is performed by this script.'
}
