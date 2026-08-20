# Work Selection and Build Sequence

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-05` |
| Status | `ACTIVE` |
| Pack version | `1.3.0` |
| Primary domains | `work_selection`, `budgeting` |
| Governing entry point | `AGENTS.md` |

## Use the existing control plane

Project Control Kernel determines deterministic eligibility, readiness, scope findings, and completion projection. Build Sequencer ranks ready work using dependency, priority, critical-path, risk, deadline, unblock, duration, and cohesion data. The scheduler admits conflict-safe lanes after readiness; it does not create readiness.

Do not replace these systems with a new backlog file, status ledger, spreadsheet, or agent-maintained queue.

## Read-only selection commands

```bash
PYTHONPATH=src python -m project_pipeline control evaluate --root .
PYTHONPATH=src python -m project_pipeline control sequence --root .
PYTHONPATH=src python -m project_pipeline control scope --root .
PYTHONPATH=src python -m project_pipeline control completion --root .
PYTHONPATH=src python -m project_pipeline control ready-plan --root .
```

A readiness transition uses the governed `ready-apply` path with explicit apply, approval, and optimistic state version. Never mutate issue state merely to make a task selectable.

## Selection order

Choose among eligible items approximately in this order:

1. P0 security, corruption, release, data-integrity, or control-plane blockers;
2. critical-path work;
3. work that unlocks multiple dependencies;
4. P1 high-impact implementation or risk reduction;
5. normal planned work;
6. lower-priority enhancement or cleanup.

Priority, defect severity, security severity, and execution risk are distinct dimensions. Do not infer one from another.

## Selection constraints

Before claiming an item, confirm:

- it is not a structural epic;
- dependencies and blockers are represented accurately;
- no active lane already owns overlapping work;
- implementation is not already complete under another issue;
- the change can form a coherent vertical slice;
- resources and environment are available;
- expected cost fits the budget policy;
- required context and verification are attainable.

Bulk-audit a compatible candidate set before admitting implementation. Compare accepted requirements with existing code, tests, evidence, and implementation mappings. When these already prove the work, Project Control reports `RECONCILIATION_REQUIRED`; do not start another implementation lane. Reconcile at least the machine-policy batch minimum in one bounded change unless a real implementation or defect correction is also present.

If the top-ranked item is blocked, record the blocker and select the next independent eligible item. Do not stop the project unless the blocker is globally critical.

## Vertical slices and cohesion

Prefer a complete behavior with code, tests, generated artifacts, documentation, traceability, and evidence over scattered partial edits across unrelated components. One cohesive PR may satisfy multiple linked tasks when acceptance and rollback boundaries align.

The unit of delivery is the cohesive vertical slice, not a Jira lifecycle arrow. Compatible transitions inside a slice are bookkeeping and share one branch, PR, expensive gate, independent review, merge, and post-merge reconciliation. Never advance one already-complete item through a branch or PR per state.

Admit a candidate only at an acceptance boundary: exact criterion, falsifier, distinct rollback/deduplication identity, and exact-main evidence. If two proposed units share that identity, merge them and count once. Shared files or a shared parent requirement do not create credit.

Prefer one cohesive vertical slice over file-sized or lifecycle-sized tasks. Do not split one behavior into material, process, reconciliation, and cleanup PRs. WIP remains the scheduler-safe default of two implementation lanes and at most one merge-ready PR.

Do not bounce between unrelated components to maximize apparent activity.

## Budget-aware dispatch

Use deterministic local tooling for deterministic work. Consult Budget Governor before paid model, provider, cloud, or high-cost compute work. Unknown price is not zero. Preserve protected reserve and obey hard-stop behavior. Stronger model reasoning is justified for complex architecture, difficult debugging, high-risk review, or ambiguous accepted requirements; it is not justified for formatting or deterministic lookup.

Useful read-only budget commands include status, forecast, preflight, metrics, and impact. Spend leases or limit changes require policy and authorization.

## WIP and throughput

The default is two isolated implementation lanes, bounded by scheduler safety, available workers, resource conflicts, and merge throughput. A third lane requires explicit capacity evidence. Review and integration must keep pace; unfinished parallel work is integration debt.

## Discovered gaps

Search existing Jira, indexes, plans, requirements, and related implementation before creating work. A new item is justified only by a real traceable scope gap with correct parent, acceptance criteria, verification, dependencies, risk, and authority classification. Avoid micro-ticket proliferation.
