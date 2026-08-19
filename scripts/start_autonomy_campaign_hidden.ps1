# Launch or recover the autonomous campaign controller in a hidden Windows process.
# Does not fabricate elapsed time. 24/72-hour attestation remains wall-clock only.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [Parameter(Mandatory = $true)]
    [string]$Database,
    [Parameter(Mandatory = $true)]
    [string]$StatePath,
    [Parameter(Mandatory = $true)]
    [string]$LogDirectory,
    [Parameter(Mandatory = $true)]
    [string]$EvidencePath,
    [Parameter(Mandatory = $true)]
    [string]$Pp384Evidence,
    [string]$CampaignId = "",
    [string]$ExpectedSha = "",
    [string]$ExpectedTree = "",
    [string]$StatusPath = "",
    [double]$HeartbeatSeconds = 30,
    [int]$Cycles = 0,
    [string]$StopFile = "",
    [string]$ServiceIdentity = "schtasks:ProjectPipelineAutonomyCampaign",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$python = (Resolve-Path -LiteralPath $PythonExe).Path
$script = Join-Path -Path $root -ChildPath "scripts\run_autonomy_campaign.py"
if (-not (Test-Path -LiteralPath $script)) {
    throw "campaign runner is missing: $script"
}
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Database) | Out-Null
New-Item -ItemType Directory -Force -Path $StatePath | Out-Null
if (-not $StatusPath) {
    $StatusPath = Join-Path -Path $LogDirectory -ChildPath "pp385_campaign_status.json"
}

$stdout = Join-Path -Path $LogDirectory -ChildPath "campaign.stdout.log"
$stderr = Join-Path -Path $LogDirectory -ChildPath "campaign.stderr.log"
$pidFile = Join-Path -Path $LogDirectory -ChildPath "campaign.pid"
$env:PYTHONPATH = Join-Path -Path $root -ChildPath "src"

$startArgs = @(
    $script,
    "start",
    "--database", $Database,
    "--state-path", $StatePath,
    "--evidence-path", $EvidencePath,
    "--pp384-evidence", $Pp384Evidence,
    "--repository-root", $root,
    "--heartbeat-seconds", ([string]$HeartbeatSeconds),
    "--service-identity", $ServiceIdentity
)
$recoverArgs = $null
if ($CampaignId) {
    $recoverArgs = @(
        $script,
        "recover",
        "--database", $Database,
        "--campaign-id", $CampaignId,
        "--repository-root", $root,
        "--heartbeat-seconds", ([string]$HeartbeatSeconds)
    )
}

$payload = [ordered]@{
    working_directory = $root
    python_exe = $python
    window_style = "Hidden"
    argument_list = $(if ($recoverArgs) { $recoverArgs } else { $startArgs })
    stdout_log = $stdout
    stderr_log = $stderr
    pid_file = $pidFile
    status_path = $StatusPath
    simulated_elapsed = $false
    service_identity = $ServiceIdentity
    campaign_id = $CampaignId
    expected_sha = $ExpectedSha
    expected_tree = $ExpectedTree
}
if ($DryRun) {
    $payload | ConvertTo-Json -Depth 6
    exit 0
}

function Invoke-CampaignJson {
    param([string[]]$ArgumentList)
    $started = Start-Process -FilePath $python -ArgumentList $ArgumentList -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Wait-Process -Id $started.Id -Timeout 180 -ErrorAction SilentlyContinue
    $raw = ""
    if (Test-Path -LiteralPath $stdout) {
        $raw = Get-Content -LiteralPath $stdout -Raw
    }
    $id = $null
    if ($raw -match '"campaign_id"\s*:\s*"([^"]+)"') {
        $id = $Matches[1]
    }
    return $id
}

$resolvedId = $CampaignId
if ($recoverArgs) {
    $resolvedId = Invoke-CampaignJson -ArgumentList $recoverArgs
} else {
    $resolvedId = Invoke-CampaignJson -ArgumentList $startArgs
}
if (-not $resolvedId) {
    throw "campaign launcher could not read a campaign_id from controller output"
}

$runArgs = @(
    $script,
    "run",
    "--database", $Database,
    "--campaign-id", $resolvedId,
    "--repository-root", $root,
    "--heartbeat-seconds", ([string]$HeartbeatSeconds)
)
if ($Cycles -gt 0) {
    $runArgs += @("--cycles", ([string]$Cycles))
}
if ($StopFile) {
    $runArgs += @("--stop-file", $StopFile)
}
$process = Start-Process -FilePath $python -ArgumentList $runArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$pidPayload = [ordered]@{
    process_id = $process.Id
    campaign_id = $resolvedId
    executable = $python
}
$pidPayload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $pidFile -Encoding utf8
& $python $script "project-status" --database $Database --campaign-id $resolvedId --repository-root $root --status-path $StatusPath | Out-Null
[ordered]@{
    pid = $process.Id
    pid_file = $pidFile
    stdout_log = $stdout
    stderr_log = $stderr
    working_directory = $root
    campaign_id = $resolvedId
    status_path = $StatusPath
    user_action_required = $false
    stop_command = @(
        $python,
        $script,
        "stop",
        "--database", $Database,
        "--repository-root", $root,
        "--campaign-id", $resolvedId
    )
} | ConvertTo-Json -Depth 6
