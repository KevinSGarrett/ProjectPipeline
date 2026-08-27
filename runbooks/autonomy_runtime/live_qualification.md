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

Exact PP-379 public bytes are verified by the recovery evaluator; arbitrary JSON
copied to expected paths cannot pass. A release-candidate qualification reads a
separate attestation source and writes its derived records only below the
worker-owned durable or disposable root. It never materializes ignored evidence
or `.local` state inside the candidate checkout.

Pass a worker-owned `--disposable-root` outside the candidate for every run;
the command rejects candidate-nested writable roots. Evidence output defaults
under that disposable root and may likewise be redirected only to an external
worker-owned location.

## Coordinator-owned governance relay

When the CPU worker does not hold a GitHub or Jira credential, the coordinator
performs each governed read/write/readback and writes a fresh, signed,
candidate-bound receipt. Transfer only that receipt and its signature through
the approved content-addressed channel. The credential, signing key, and their
plaintext values remain on the coordinator. The worker rejects a receipt whose
signature, age, candidate SHA/tree, or write/readback proof does not match.

Create the GitHub receipt on the authenticated coordinator using its
machine-bound signing-key reference:

```powershell
python scripts/run_coordinator_github_governance_probe.py `
  --root . --output <receipt.json> --signature <receipt.sig> `
  --signing-key <machine-bound-signing-key>
```

Create the matching Jira receipt through the existing coordinator probe. On the
CPU worker, provide both verified receipt pairs to the live-qualification
command. A scheduler must regenerate the short-lived receipts before each
governance probe; it must never reuse stale evidence.

## Run

```powershell
$env:PYTHONPATH = "src"
python -m project_pipeline attestation recover --root .
python scripts/run_live_qualification.py --root . `
  --disposable-root <worker-owned-disposable-root> `
  --attestation-source-root <verified-public-evidence-root> `
  --durable-dir <worker-owned-durable-root> `
  --coordinator-github-receipt <github-receipt.json> `
  --coordinator-github-signature <github-receipt.sig> `
  --coordinator-jira-receipt <jira-receipt.json> `
  --coordinator-jira-signature <jira-receipt.sig>
python scripts/run_live_qualification.py --root . --write-evidence `
  --disposable-root <worker-owned-disposable-root> `
  --attestation-source-root <verified-public-evidence-root> `
  --durable-dir <worker-owned-durable-root> `
  --coordinator-github-receipt <github-receipt.json> `
  --coordinator-github-signature <github-receipt.sig> `
  --coordinator-jira-receipt <jira-receipt.json> `
  --coordinator-jira-signature <jira-receipt.sig>
```

## Tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q tests/test_attestation_recovery.py tests/test_autonomy_live_qualification.py tests/test_cursor_cli_qualification.py
```
