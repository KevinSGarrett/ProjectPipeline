# Autonomous Operating Contract

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-02` |
| Status | `ACTIVE` |
| Pack version | `1.3.0` |
| Primary domains | `autonomous_cycle`, `definition_of_ready` |
| Governing entry point | `AGENTS.md` |

## Required execution cycle

```text
REHYDRATE
→ PREFLIGHT
→ SELECT ELIGIBLE WORK
→ RETRIEVE BOUNDED CONTEXT
→ CLAIM RESOURCES
→ CREATE OR REUSE BRANCH AND WORKTREE
→ IMPLEMENT
→ TARGETED TEST
→ SELF-REVIEW
→ INDEPENDENT OR RISK-BASED REVIEW
→ REQUIRED VALIDATION
→ CREATE OR UPDATE PR
→ MERGE GATE
→ MERGE
→ POST-MERGE VERIFICATION
→ JIRA AND EVIDENCE RECONCILIATION
→ CLEANUP
→ SELECT NEXT WORK
```

A cycle does not voluntarily stop at a review request, PR gate, Jira transition, branch cleanup, formatting/test task, or other automatable routine action. A bounded lane may become `BLOCKED_EXTERNAL` only when a required external capability is objectively unavailable; preserve it, schedule autonomous recheck, and continue every other eligible lane. A cycle handoff is an autonomous checkpoint, not an assignment of work to the operator.

## Operating invariants

- ProjectPipeline deterministic services own state transitions, readiness, resource admission, external-write intent, evidence evaluation, and completion.
- Models and agents are bounded workers or advisors, not canonical authorities.
- State required after restart lives outside chat.
- Every active implementation lane has one owner, work identity, branch, worktree, base SHA, resource claim set, and merge target.
- The same remote mutation has one idempotency identity and reconciliation path.
- Every sustained work period produces accepted progress, blocker reduction, valid evidence, corrected diagnosis, or a typed external-precondition record while unaffected work continues.
- Process is proportional to risk. Low-risk work is fast; high-risk work receives stronger independence and recovery proof.

## Definition of Ready

Before implementation, establish:

- owning work item and parent;
- accepted requirements and authority classification;
- acceptance criteria and verification methods;
- dependency and blocker state;
- applicable plan sections, decisions, policies, and contracts;
- known affected resources and a claimable workspace;
- risk classification and test strategy;
- intended external mutations and their authority;
- expected evidence and integration boundary.

Do not demand perfect paperwork where behavior is clear and safe. Do not use urgency to proceed with unknown authority, ownership, or destructive scope.

## Role model

Use roles only when they improve independence or throughput:

- Explorer: bounded discovery and source retrieval, no implementation authority by default.
- Implementer: owns the cohesive change and targeted tests.
- Verification worker: independently reproduces acceptance where risk requires.
- Security reviewer: evaluates authority, egress, secrets, supply chain, and abuse cases.
- Integration worker: owns merge-order and integrated-main verification.
- Release verifier: evaluates artifacts, installation, provenance, and rollback.

One session may perform several roles sequentially for low-risk work. High-risk work must preserve meaningful independence required by policy.

## Work-in-progress control

Use scheduler-safe lanes and the policy in `policies/BRANCH_PR_POLICY.json`. The normal starting cap is two implementation lanes, with a third only when workers, resource isolation, and merge throughput support it. Do not open dozens of branches or PRs because the backlog is large.

## Progress and housekeeping

Housekeeping is bounded. Perform it after merge, when hygiene creates real risk, during a scheduled maintenance window, or before release. Renaming, reorganizing, regenerating, or reporting without accepted progress is not a substitute for implementation.

Measure sustained work using objective before/after repository facts. A positive progress delta requires newly satisfied acceptance, eliminated failure or blocker, newly passing required behavior, integrated implementation, or durable evidence for one of those changes. Jira state movement, branches, PRs, repeated validation, regenerated projections, claims, snapshots, and bookkeeping are activity with zero progress unless they accompany such an objective change. Enforce the administrative-work budget in `config/assurance_policy.json` and stop or change strategy when the zero-progress limit is reached.

## Cycle workload (Cursor cycles 16+)

Cursor combined-agent cycles use a fixed Cycle 1-15 high-water baseline identified as `CURSOR_CYCLES_001_015_HIGH_WATER`. The independently validated baseline is 24 weighted substantive points across 7 distinct units. Later cycles apply a noncompounding 2000-milli (2x) multiplier, requiring at least 48 weighted points and 14 distinct substantive acceptance units unless deterministic endgame saturation completes the project with less remaining legitimate scope.

A substantive acceptance unit is one unique accepted production behavior with a falsifiable before/after boundary, a distinct rollback/deduplication identity, and exact-main evidence. Weight is 1-4: production behavior, plus a real OS/process/network/external/persistent boundary, plus P0/critical/security/recovery/concurrency/release risk, plus closure of an accepted requirement or mandatory Completion Gate environment.

Zero credit: commits, PRs, branches, worktrees, Jira transitions/comments, manifests, checksums, generated projections, handoff prose, dependency installation by itself, repeated validations, cleanup, lifecycle-only reconciliation, timers, heartbeats, or splitting one behavior across files/PRs. Administrative credit is always 0.

If fewer legitimate units or points remain, finish every remaining accepted requirement, every mandatory qualification environment, the governed 4h → 24h → 72h ladder, release, post-release verification, Jira/GitHub convergence, and the deterministic Completion Gate. Never invent or micro-split work to hit the meter. Do not stop for a person; continue through autonomous policy.

## Autonomous decisions and routine-action grant

Do not interrupt the operator for routine development work. Use plans, ADRs, policy, source, and professional judgment. Routine actions are autonomously authorized when the exact target is identified, ownership and scope are bounded, applicable implementation and evidence are complete, the scope gate and integrated-main verification pass when relevant, credentials are already provisioned through approved references, the mutation is deterministic and idempotent, and its result can be read back.

This standing grant covers local edits and commits, generated artifacts, policy-compatible dependency installation, tests, linting, formatting, PR creation/update/merge, Jira lifecycle and `Done` reconciliation, eligible branch/worktree cleanup, and other ordinary development mechanics. Risk-tier checks and independent verification still apply, but neither requires a human actor. If an external capability is absent, record a typed external precondition without asking the operator to perform work, continue independent work, and re-evaluate through the autonomous scheduler.

## Completion boundary

The control projection may identify ready, active, blocked, or apparently completed work. The deterministic Completion Gate is the final authority for completion. See `12_TESTING_VERIFICATION_AND_COMPLETION.md`.
