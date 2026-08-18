# PLAN-CTRL-002 — Project Control Kernel and Build Sequencer

- **Plan ID:** `PLAN-CTRL-002`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus required implementation detail
- **Source basis:** `SRC-003:L000040-L000083`, `SRC-003:L000225-L000371`, `SRC-014:L000210-L000373`, `SRC-014:L000378-L000748`, `SRC-014:L000859-L000946`, `GOV-001:L000423-L000435`

## PLAN-CTRL-002:SEC-01 Canonical control authority

The Project Control Kernel is the deterministic authority for runtime project-state admissibility, task eligibility, readiness, accepted dependency truth, scope-reconciliation findings, and completion recomputation. Probabilistic systems may propose sequence or remediation, but they cannot directly commit canonical transitions.

## PLAN-CTRL-002:SEC-02 Accepted work graph

The Build Sequencer constructs a directed graph from source-controlled work identities and accepted blocking dependencies. Every dependency endpoint must exist. Blocking cycles are invalid and fail sequencing. Non-blocking iterative relationships remain outside the dependency DAG. NetworkX supplies bounded graph primitives behind Project Pipeline-owned semantics; it does not own eligibility or transition authority.

## PLAN-CTRL-002:SEC-03 Eligibility and readiness

Eligibility first excludes terminal, already-active, failed, blocked, unaccepted, policy-denied, and `BLOCKED_EXTERNAL` work. Readiness is then computed from dependency completion, explicit blockers, policy-qualified approvals, required context, resources, and environment availability. An externally blocked item is owned by autonomous recheck and does not prevent independent work elsewhere from becoming ready.

## PLAN-CTRL-002:SEC-04 Critical-path analysis

Critical-path calculations operate on the validated dependency DAG. Declared duration estimates are used when present. When duration evidence is unavailable, a documented equal-duration heuristic is used only to expose dependency-depth critical-path structure; it is not presented as an actual delivery-time forecast. Earliest-finish and slack facts are deterministic and reproducible for the same graph inputs.

## PLAN-CTRL-002:SEC-05 Priority and build sequencing

Ready work is ranked deterministically from explicit priority, critical-path membership, deadline pressure when supplied, risk, downstream unblock value, and declared expected duration when supplied. The score breakdown is retained so ranking is explainable. Stable work IDs break exact ties. Scheduling/resource admission remains a separate downstream responsibility.

## PLAN-CTRL-002:SEC-06 Scope reconciliation

The control plane compares accepted requirements, Jira work, dependency references, implementation state, and completion evidence. Missing requirement/work mappings, unknown dependencies, completed work without evidence, and implemented requirements without mapped artifacts are represented as explicit findings rather than silently repaired.

## PLAN-CTRL-002:SEC-07 Completion recomputation

Completion is recomputed from accepted requirement dispositions and persistent work state. The Control Kernel may determine that a project is eligible to enter independent completion verification, but it cannot satisfy the Completion Gate itself. Final completion authority remains separated from implementation and sequencing authority.

## PLAN-CTRL-002:SEC-08 Persistence and change detection

Control evaluations are persisted as immutable snapshots with graph and semantic fingerprints, ordered ready work, critical-path facts, scope findings, and completion projection. Re-evaluation after accepted changes produces a new deterministic projection without mutating historical evidence. Runtime transitions retain optimistic version checks in canonical state persistence.

## PLAN-CTRL-002:SEC-09 Operator and machine interfaces

CLI operations expose evaluation, sequence, readiness, scope, completion, status, and readiness-transition planning. State-changing readiness transitions are separate from read-only evaluation and require an explicit apply/approval invocation. Machine-readable schemas permit future API and Command Center reuse without duplicating control semantics.

## PLAN-CTRL-002:SEC-10 Verification and failure behavior

Tests cover graph cycles, unknown dependencies, independent progress around blocked work, readiness predicates, deterministic ordering, critical-path calculations, priority factors, scope drift, completion projection, migrations, persistence, CLI behavior, and repository self-validation. Invalid graph or state inputs fail closed; no remote Jira, GitHub, AWS, provider, or paid-service mutation is required for this control-plane slice.
