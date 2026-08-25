# Register or remove a namespaced hidden scheduled task that recovers a bound campaign.
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
    [string]$CampaignId = "",
    [string]$ExpectedSha = "",
    [string]$ExpectedTree = "",
    [string]$Fence = "",
    [string]$ServiceIdentity = "schtasks:ProjectPipelineAutonomyCampaign",
    [string]$StatePath = "",
    [string]$EvidencePath = "",
    [string]$Pp384Evidence = "",
    [string]$StatusPath = "",
    [string]$RuntimeEnvironmentFile = "",
    [int]$IntervalMinutes = 5,
    [int]$RepetitionDays = 31,
    [int]$Cycles = 0,
    [double]$HeartbeatSeconds = 60,
    [double]$HeartbeatMaxAgeSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$python = (Resolve-Path -LiteralPath $PythonExe).Path
$probe = Join-Path -Path $root -ChildPath "scripts\autonomy_campaign_recovery_probe.py"
if (-not (Test-Path -LiteralPath $probe)) {
    throw "recovery probe is missing: $probe"
}
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$pidFile = Join-Path -Path $LogDirectory -ChildPath "campaign.pid"
$healthLog = Join-Path -Path $LogDirectory -ChildPath "campaign.recovery.log"
$configPath = Join-Path -Path $LogDirectory -ChildPath "recovery_probe.json"
if (-not $StatusPath) {
    $StatusPath = Join-Path -Path $LogDirectory -ChildPath "pp385_campaign_status.json"
}
if (-not $StatePath) { $StatePath = Join-Path -Path $LogDirectory -ChildPath "state" }
if (-not $EvidencePath) { $EvidencePath = Join-Path -Path $LogDirectory -ChildPath "evidence" }
if (-not $Pp384Evidence) { $Pp384Evidence = Join-Path -Path $LogDirectory -ChildPath "pp384.json" }
$runtimeEnvironmentPath = ""
$windowsIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$scheduledPrincipalIdentity = $windowsIdentity.Name
$scheduledPrincipalSid = $windowsIdentity.User.Value
if ($RuntimeEnvironmentFile) {
    $runtimeEnvironmentPath = (Resolve-Path -LiteralPath $RuntimeEnvironmentFile).Path
    if (-not (Test-Path -LiteralPath $runtimeEnvironmentPath -PathType Leaf)) {
        throw "campaign runtime environment file is unavailable"
    }
}

$config = [ordered]@{
    schema_version = "1.0.0"
    task_name = $TaskName
    repository_root = $root
    python_exe = $python
    database = $Database
    campaign_id = $CampaignId
    expected_sha = $ExpectedSha
    expected_tree = $ExpectedTree
    fence = $Fence
    service_identity = $ServiceIdentity
    state_path = $StatePath
    evidence_path = $EvidencePath
    pp384_evidence_path = $Pp384Evidence
    status_path = $StatusPath
    pid_path = $pidFile
    log_directory = $LogDirectory
    heartbeat_seconds = $HeartbeatSeconds
    heartbeat_max_age_seconds = $HeartbeatMaxAgeSeconds
    cycles = $Cycles
    runtime_environment_file = $runtimeEnvironmentPath
    scheduled_principal_identity = $scheduledPrincipalIdentity
    scheduled_principal_sid = $scheduledPrincipalSid
    simulated_elapsed = $false
}
$payload = [ordered]@{
    task_name = $TaskName
    interval_minutes = $IntervalMinutes
    repetition_days = $RepetitionDays
    window_style = "Hidden"
    pid_file = $pidFile
    health_log = $healthLog
    config_path = $configPath
    probe = $probe
    python_exe = $python
    database = $Database
    campaign_id = $CampaignId
    expected_sha = $ExpectedSha
    expected_tree = $ExpectedTree
    fence = $Fence
    status_path = $StatusPath
    runtime_environment_file = $runtimeEnvironmentPath
    scheduled_principal_identity = $scheduledPrincipalIdentity
    scheduled_principal_sid = $scheduledPrincipalSid
    simulated_elapsed = $false
}

if ($Action -eq "plan") {
    $payload | ConvertTo-Json -Depth 6
    exit 0
}

if ($Action -eq "status") {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $info = $null
    if ($task) { $info = Get-ScheduledTaskInfo -TaskName $TaskName }
    $registeredAction = if ($task) { @($task.Actions)[0] } else { $null }
    [ordered]@{
        task_name = $TaskName
        registered = [bool]$task
        enabled = if ($task) { [bool]$task.Settings.Enabled } else { $false }
        hidden = if ($task) { [bool]$task.Settings.Hidden } else { $false }
        principal_identity = if ($task) { $task.Principal.UserId } else { $null }
        expected_principal_identity = $scheduledPrincipalIdentity
        scheduled_principal_sid = $scheduledPrincipalSid
        principal_identity_matches_expected = if ($task) { ($task.Principal.UserId -ieq $scheduledPrincipalIdentity) -or ($task.Principal.UserId -ieq $scheduledPrincipalSid) } else { $false }
        principal_logon_type = if ($task) { $task.Principal.LogonType.ToString() } else { $null }
        principal_run_level = if ($task) { $task.Principal.RunLevel.ToString() } else { $null }
        action_executable = if ($registeredAction) { $registeredAction.Execute } else { $null }
        action_arguments = if ($registeredAction) { $registeredAction.Arguments } else { $null }
        working_directory = if ($registeredAction) { $registeredAction.WorkingDirectory } else { $null }
        execution_time_limit = if ($task) { $task.Settings.ExecutionTimeLimit.ToString() } else { $null }
        multiple_instances = if ($task) { $task.Settings.MultipleInstances.ToString() } else { $null }
        pid_file = $pidFile
        pid_file_exists = (Test-Path -LiteralPath $pidFile)
        status_path = $StatusPath
        last_task_result = if ($info) { $info.LastTaskResult } else { $null }
        number_of_missed_runs = if ($info) { $info.NumberOfMissedRuns } else { $null }
        next_run_time_utc = if ($info) { $info.NextRunTime.ToUniversalTime().ToString("o") } else { $null }
        user_action_required = $false
    } | ConvertTo-Json -Depth 4
    exit 0
}

if ($Action -eq "uninstall") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    [ordered]@{ task_name = $TaskName; registered = $false; user_action_required = $false } | ConvertTo-Json
    exit 0
}

# The recovery probe retargets this file atomically after a legitimate
# stale-runner takeover.  Only installation may author a new binding; read and
# uninstall operations must not silently restore an obsolete parent campaign.
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($configPath, (($config | ConvertTo-Json -Depth 6) + [Environment]::NewLine), $utf8NoBom)

if ($RepetitionDays -lt 1 -or $RepetitionDays -gt 31) {
    throw "repetition duration must be a finite 1-31 day value accepted by Windows Task Scheduler"
}
$exec = New-ScheduledTaskAction -Execute $python -Argument "`"$probe`" --config `"$configPath`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days $RepetitionDays)
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $scheduledPrincipalSid -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $exec -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
[ordered]@{
    task_name = $TaskName
    registered = $true
    pid_file = $pidFile
    health_log = $healthLog
    config_path = $configPath
    status_path = $StatusPath
    runtime_environment_file = $runtimeEnvironmentPath
    principal_identity = $principal.UserId
    principal_sid = $scheduledPrincipalSid
    principal_logon_type = "Interactive"
    principal_run_level = "Limited"
    execution_time_limit = "PT4M"
    user_action_required = $false
} | ConvertTo-Json
