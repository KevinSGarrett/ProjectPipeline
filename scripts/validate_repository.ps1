
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $Root "src"
python -m project_pipeline validate --root $Root
python -m unittest discover -s (Join-Path $Root "tests") -v
