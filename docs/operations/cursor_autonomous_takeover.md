# Cursor autonomous takeover

Cursor is a replaceable execution provider inside ProjectPipeline. It is not the project memory, work selector, external-write authority, or completion judge.

## Safe activation sequence

1. Complete a read-only takeover audit and resolve or transfer every active worktree and resource claim.
2. Validate the tracked Cursor package with `python scripts/cursor_takeover.py validate --root .`.
3. Repair the source-derived product model and bulk-reconcile already implemented work.
4. Install and authenticate Cursor Agent CLI (`agent` on current native Windows releases; the adapter also recognizes the legacy `cursor-agent` name), enable Privacy Mode, and keep the provider quarantined.
5. Run one bounded fixture slice with external writes disabled.
6. Qualify the golden journey, controlled GitHub/Jira adapters, restart recovery, Windows behavior, then 4-hour, 24-hour, and 72-hour unattended stages.
7. Change provider activation to `QUALIFIED` only through a governed review after evidence is registered.

## Private-attestation relay

Some provider attestation records are intentionally private coordinator evidence and are excluded
from public source archives.  Before a CPU-hosted PP-384 run, the coordinator may create a fresh,
candidate-bound receipt with `scripts/run_coordinator_attestation_relay.py`.  The receipt contains
only the approved immutable digest, byte-length, policy identity, candidate identity, and a
coordinator signature; it never contains or restores the private evidence bytes.  The CPU accepts
the relay only when the signature, receipt digest, policy fields, candidate SHA/tree, and freshness
window all verify.  An invalid or missing relay remains a fail-closed qualification finding.

The supervisor rehydrates durable state, runs deterministic validation, uses Control ordering, audits each candidate against its own declared artifacts and tests, selects genuinely missing work, creates at most two conflict-safe lanes, verifies one cohesive slice, opens one PR, runs the expensive gate once, reconciles state in a batch, and repeats.

Initialize and update its durable local state only through the governed helper:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\cursor_takeover.py state-init --root .
.\.venv\Scripts\python.exe scripts\cursor_takeover.py state-record --root . --objective-progress-units 1 --completion-gate NOT_COMPLETE
```

The stop hook may continue only from that durable state. Two zero-progress records change the supervisor status to `PLANNER_DIAGNOSIS_REQUIRED` and suppress further automatic continuation.

The stop hook is convenience automation, not an authority or availability guarantee. Cursor cloud agents do not consistently run lifecycle hooks, and Windows releases have had stop-hook continuation defects. Scheduled or event-driven wake-ups must therefore rehydrate the same durable supervisor state and apply the same two-cycle stop condition.

## Non-negotiable stops

- Two consecutive cycles without objective product progress stop autonomous dispatch and require planner/model diagnosis.
- Lifecycle transitions, generated views, evidence registration, snapshots, or manifest refreshes never constitute a standalone deliverable.
- Cloud agents cannot receive secrets or local-only data and cannot prove Windows behavior.
- Cursor cannot directly mutate GitHub or Jira; ProjectPipeline plan/apply/receipt/readback adapters retain that authority.
- Completion requires all deterministic Completion Gate questions, including a verified 72-hour unattended end-to-end qualification.

Generate the current takeover prompt with:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\cursor_takeover.py prompt --root .
```
