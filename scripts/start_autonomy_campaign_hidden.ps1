# Launch the autonomous campaign controller in a hidden Windows process.
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

$stdout = Join-Path -Path $LogDirectory -ChildPath "campaign.stdout.log"
$stderr = Join-Path -Path $LogDirectory -ChildPath "campaign.stderr.log"
$pidFile = Join-Path -Path $LogDirectory -ChildPath "campaign.pid"

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

$payload = [ordered]@{
    working_directory = $root
    python_exe = $python
    window_style = "Hidden"
    argument_list = $startArgs
    stdout_log = $stdout
    stderr_log = $stderr
    pid_file = $pidFile
    simulated_elapsed = $false
    service_identity = $ServiceIdentity
}
if ($DryRun) {
    $payload | ConvertTo-Json -Depth 6
    exit 0
}

$env:PYTHONPATH = Join-Path -Path $root -ChildPath "src"
$started = Start-Process -FilePath $python -ArgumentList $startArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Wait-Process -Id $started.Id -Timeout 120 -ErrorAction SilentlyContinue
$campaignId = $null
if (Test-Path -LiteralPath $stdout) {
    $raw = Get-Content -LiteralPath $stdout -Raw
    if ($raw -match '"campaign_id"\s*:\s*"([^"]+)"') {
        $campaignId = $Matches[1]
    }
}
$runArgs = @(
    $script,
    "run",
    "--database", $Database,
    "--campaign-id", $campaignId,
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
[System.IO.File]::WriteAllText($pidFile, [string]$process.Id)
[ordered]@{
    pid = $process.Id
    pid_file = $pidFile
    stdout_log = $stdout
    stderr_log = $stderr
    working_directory = $root
    campaign_id = $campaignId
    stop_command = @(
        $python,
        $script,
        "stop",
        "--database", $Database,
        "--repository-root", $root,
        "--campaign-id", $campaignId
    )
} | ConvertTo-Json -Depth 6
