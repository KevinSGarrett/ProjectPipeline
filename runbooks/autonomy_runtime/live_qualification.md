# Autonomy Runtime Live Qualification (PP-384 Stage-C)

## Scope

Stage-C qualifies attestation-free local-real paths:

- Windows service foreground lifecycle (plan, checkpoint, stale-PID recovery, restart)
- Command Center durable-state truth projection (including Windows service health)
- Local subprocess provider dispatch (`local_test_provider`)
- Honest external gates for GitHub/Jira (governed write/readback when credentials resolve; otherwise `BLOCKED_EXTERNAL`)
- Cursor CLI provider remains `HUMAN_REQUIRED` until PP-379 attestation evidence exists

## Run

```powershell
$env:PYTHONPATH = "src"
python scripts/run_live_qualification.py --root .
python scripts/run_live_qualification.py --root . --write-evidence
```

## Expected outcomes

| Stage | Expected outcome |
| --- | --- |
| `windows_service_foreground` | `PASSED` |
| `command_center_truth` | `PASSED` |
| `local_provider_dispatch` | `PASSED` |
| `github_jira_governance` | `PASSED` when GitHub branch create/delete and Jira comment write both read back; else `BLOCKED_EXTERNAL` |
| `cursor_cli_provider_dispatch` | `HUMAN_REQUIRED` |

Evidence is written to `evidence/autonomy_runtime/live_qualification/live_qualification_latest.json` when `--write-evidence` is used. Never fabricate attestation or provider qualification artifacts.

## Tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q tests/test_autonomy_live_qualification.py
```
