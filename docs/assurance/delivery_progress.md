# Delivery Progress Governor

ProjectPipeline measures delivery using objective repository deltas, not activity counts. This implements the adopted original-pack principles in `SRC-008:L000156-L000196` (Progress Delta) and `SRC-008:L000295-L000368` (hygiene budget). The original archive remains reference-only under `INPUT-KNOWLEDGE-001`; its contents do not override the accepted requirement catalog or current operator direction.

## Objective progress

`calculate_progress_delta` compares accepted before/after facts. Progress is positive only when the candidate adds one or more of:

- implemented accepted requirements;
- verified acceptance criteria or evidence;
- removed blockers or eliminated failures;
- newly passing required tests;
- integrated implementation.

Jira transitions, branches, pull requests, CI runs, snapshots, claims, regenerated indexes, and manifest refreshes are administrative activity. They contribute no progress by themselves. The gate reports all administrative units for evidence honesty, while applying the 10% ceiling to the noncritical subset. Required integrity projections remain visible in the total but do not consume the noncritical budget; discretionary lifecycle churn does.

## Admission and pull-request controls

Before implementation, Project Control checks whether all linked requirements are already implemented, implementation paths exist, and evidence is linked. Such work becomes `RECONCILIATION_REQUIRED` and is excluded from fresh implementation sequencing.

The delivery gate evaluates the exact Git base and candidate head. It denies a single-item lifecycle-only PR. Unrelated source or test churn cannot disguise that transition: when lifecycle state changes, the candidate must change the issue's own declared implementation artifact and a required test resolved through `tests/TEST_CATALOG.json`. Reconciliation-only changes require at least three compatible, evidence-backed items in one bounded batch. A governance-only correction remains eligible only without lifecycle changes and with a governed instruction/policy change, its instruction-manifest refresh, and the instruction-system regression test.

Run locally after committing the candidate:

```powershell
$env:PYTHONPATH = "src"
python -m project_pipeline assurance delivery-gate --root . --base-ref <base-sha> --head-ref HEAD
```

## Time and verification budgets

The canonical settings are in `config/assurance_policy.json`. Two consecutive zero-progress cycles stop the current strategy. Noncritical administrative work has a 100/1000 (10%) ceiling during sustained delivery. Expensive risk-tier validation runs once at the cohesive vertical-slice boundary; targeted falsification is used during implementation.

These controls are hash-managed and instruction-validated. CI and negative regression tests fail if lifecycle-only PR denial, reconciliation batching, exact-base/head evaluation, progressless stopping, or the administration ceiling is weakened.
