# Launch the unattended qualification runner in a hidden Windows process.
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
    [ValidateSet("RECOVERY", "UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR")]
    [string]$Stage,
    [double]$HeartbeatSeconds = 30,
    [int]$Cycles = 0,
    [string]$StopFile = "",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$python = (Resolve-Path -LiteralPath $PythonExe).Path
$script = Join-Path -Path $root -ChildPath "scripts\run_autonomy_qualification.py"
if (-not (Test-Path -LiteralPath $script)) {
    throw "qualification runner is missing: $script"
}
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Database) | Out-Null
New-Item -ItemType Directory -Force -Path $StatePath | Out-Null

$stdout = Join-Path -Path $LogDirectory -ChildPath "qualification.stdout.log"
$stderr = Join-Path -Path $LogDirectory -ChildPath "qualification.stderr.log"
$pidFile = Join-Path -Path $LogDirectory -ChildPath "qualification.pid"

$argumentList = @(
    $script,
    "run",
    "--database", $Database,
    "--state-path", $StatePath,
    "--stage", $Stage,
    "--repository-root", $root,
    "--heartbeat-seconds", ([string]$HeartbeatSeconds)
)
if ($Cycles -gt 0) {
    $argumentList += @("--cycles", ([string]$Cycles))
}
if ($StopFile) {
    $argumentList += @("--stop-file", $StopFile)
}

$payload = [ordered]@{
    working_directory = $root
    python_exe = $python
    window_style = "Hidden"
    argument_list = $argumentList
    stdout_log = $stdout
    stderr_log = $stderr
    pid_file = $pidFile
    stage = $Stage
    simulated_elapsed = $false
}
if ($DryRun) {
    $payload | ConvertTo-Json -Depth 6
    exit 0
}

$env:PYTHONPATH = Join-Path -Path $root -ChildPath "src"
$process = Start-Process -FilePath $python -ArgumentList $argumentList -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
[System.IO.File]::WriteAllText($pidFile, [string]$process.Id)
[ordered]@{
    pid = $process.Id
    pid_file = $pidFile
    stdout_log = $stdout
    stderr_log = $stderr
    working_directory = $root
    stage = $Stage
    stop_command = @(
        $python,
        $script,
        "stop",
        "--database", $Database,
        "--repository-root", $root
    )
} | ConvertTo-Json -Depth 6
