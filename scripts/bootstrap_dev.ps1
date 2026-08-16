param(
  [string]$Root = (Get-Location).Path,
  [string]$Profile = "windows",
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $Root "src"

python -m project_pipeline bootstrap --root $Root --profile $Profile --prepare
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m project_pipeline dependencies validate --root $Root
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m project_pipeline schemas check --root $Root
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipTests) {
  python -m pytest -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
