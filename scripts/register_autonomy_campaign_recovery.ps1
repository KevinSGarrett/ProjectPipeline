# Register or remove a per-user hidden scheduled task that restarts a stale campaign.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("plan", "install", "uninstall", "status")]
    [string]$Action,
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [Parameter(Mandatory = $true)]
    [string]$Database,
    [Parameter(Mandatory = $true)]
    [string]$LogDirectory,
    [string]$TaskName = "ProjectPipelineAutonomyCampaign",
    [int]$IntervalMinutes = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$python = (Resolve-Path -LiteralPath $PythonExe).Path
$launcher = Join-Path -Path $root -ChildPath "scripts\start_autonomy_campaign_hidden.ps1"
$pidFile = Join-Path -Path $LogDirectory -ChildPath "campaign.pid"
$healthLog = Join-Path -Path $LogDirectory -ChildPath "campaign.recovery.log"

$payload = [ordered]@{
    task_name = $TaskName
    interval_minutes = $IntervalMinutes
    window_style = "Hidden"
    pid_file = $pidFile
    health_log = $healthLog
    launcher = $launcher
    python_exe = $python
    database = $Database
    simulated_elapsed = $false
}

if ($Action -eq "plan") {
    $payload | ConvertTo-Json -Depth 6
    exit 0
}

if ($Action -eq "status") {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    [ordered]@{
        task_name = $TaskName
        registered = [bool]$task
        pid_file = $pidFile
        pid_file_exists = (Test-Path -LiteralPath $pidFile)
    } | ConvertTo-Json -Depth 4
    exit 0
}

if ($Action -eq "uninstall") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    [ordered]@{ task_name = $TaskName; registered = $false } | ConvertTo-Json
    exit 0
}

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$actionScript = @"
`$pidFile = '$pidFile'
`$alive = `$false
if (Test-Path -LiteralPath `$pidFile) {
    `$raw = Get-Content -LiteralPath `$pidFile -Raw
    `$procId = 0
    if ([int]::TryParse(`$raw.Trim(), [ref]`$procId)) {
        `$alive = [bool](Get-Process -Id `$procId -ErrorAction SilentlyContinue)
    }
}
if (-not `$alive) {
    powershell -NoProfile -WindowStyle Hidden -File '$launcher' -RepositoryRoot '$root' -PythonExe '$python' -Database '$Database' -StatePath (Join-Path '$LogDirectory' 'state') -LogDirectory '$LogDirectory' -EvidencePath (Join-Path '$LogDirectory' 'evidence') -Pp384Evidence (Join-Path '$LogDirectory' 'pp384.json') | Out-File -FilePath '$healthLog' -Append
}
"@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($actionScript))
$exec = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -EncodedCommand $encoded"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName $TaskName -Action $exec -Trigger $trigger -Settings (New-ScheduledTaskSettingsSet -Hidden -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries) -Force | Out-Null
[ordered]@{
    task_name = $TaskName
    registered = $true
    pid_file = $pidFile
    health_log = $healthLog
} | ConvertTo-Json
