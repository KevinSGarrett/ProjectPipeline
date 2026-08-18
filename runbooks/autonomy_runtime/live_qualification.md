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

Allowed live outcomes are `PASSED`, `BLOCKED_EXTERNAL`, and `FAILED`. Legacy
`HUMAN_REQUIRED` is a compatibility storage alias only and is projected as
`BLOCKED_EXTERNAL`. Live reports must not contain `operator session`,
`await human`, or user-visible `HUMAN_REQUIRED`.

Exact PP-379 public bytes are recovered only through
`python -m project_pipeline attestation recover --root . --apply`. Arbitrary JSON
copied to the expected paths cannot pass.

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
