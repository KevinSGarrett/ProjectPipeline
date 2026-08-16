[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param([Parameter(Mandatory=$true)][string]$ProjectRoot,[Parameter(Mandatory=$true)][string]$VerifiedBackupArchive)
$ErrorActionPreference='Stop'
$root=(Resolve-Path $ProjectRoot).Path
$backup=(Resolve-Path $VerifiedBackupArchive).Path
if ($PSCmdlet.ShouldProcess($root, 'Restore a separately verified pre-upgrade backup')) {
  Write-Output "Rollback source verified as present: $backup"
  Write-Output 'Destructive replacement is intentionally not automated; follow runbooks/release_upgrade_and_rollback.md for stop, isolated restore verification, controlled replacement, and post-rollback reconciliation.'
}
