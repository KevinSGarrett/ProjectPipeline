param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Script
)

$ErrorActionPreference = 'Stop'

$gitCommon = (& git rev-parse --path-format=absolute --git-common-dir 2>$null | Select-Object -First 1)
if (-not $gitCommon) {
    $gitCommon = (& git rev-parse --git-common-dir 2>$null | Select-Object -First 1)
}
if (-not $gitCommon) {
    exit 1
}

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path -Path $gitCommon -ChildPath '..'))
$python = Join-Path -Path $projectRoot -ChildPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    exit 1
}

$candidate = Join-Path -Path (Get-Location).Path -ChildPath $Script
if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    $candidate = Join-Path -Path $projectRoot -ChildPath $Script
}
if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    exit 1
}

& $python $candidate
exit $LASTEXITCODE
