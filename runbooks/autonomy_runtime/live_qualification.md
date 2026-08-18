# Autonomy Runtime Live Qualification (PP-384)

## Scope

Live qualification is an acceptance-bearing autonomous state machine. File
existence is not qualification. An operator session is never a gate.

Stages:

- Windows service foreground lifecycle (plan, checkpoint, stale-PID recovery, restart)
- Command Center durable-state truth projection
- Local subprocess provider dispatch (`local_test_provider`)
- Governed GitHub/Jira write/readback (`PASSED` or `BLOCKED_EXTERNAL`)
- Cursor CLI provider dispatch through the registered `adapter:cursor-cli` route

Cursor CLI phases:

1. `EVIDENCE_DISCOVERY`
2. `EVIDENCE_VALIDATION`
3. `PROVIDER_CAPABILITY`
4. `LIVE_DISPATCH`
5. `RESULT_READBACK`
6. `REPLAY`
7. `CLEANUP`

Allowed live outcomes are `PASSED`, `BLOCKED_EXTERNAL`, and `FAILED`. Startup
migrates the retired human-work storage value to `BLOCKED_EXTERNAL`; no current
report, schema, plan, Jira projection, or evidence may emit it. Live reports
must not assign any routine project action outside the autonomy runtime.

Exact PP-379 public bytes are recovered only through
`python -m project_pipeline attestation recover --root . --apply`. Arbitrary JSON
copied to the expected paths cannot pass. Durable private records default to the
machine-local takeover directory when those files exist; otherwise they resolve
under `<root>/.local/state/takeover`. Override with `--durable-dir`.

## Run

```powershell
$env:PYTHONPATH = "src"
python -m project_pipeline attestation recover --root .
python -m project_pipeline attestation recover --root . --apply
python scripts/run_live_qualification.py --root .
python scripts/run_live_qualification.py --root . --write-evidence
```

## Tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q tests/test_attestation_recovery.py tests/test_autonomy_live_qualification.py tests/test_cursor_cli_qualification.py
```
