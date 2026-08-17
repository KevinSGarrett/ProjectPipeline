# Autonomous Operating Contract

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-02` |
| Status | `ACTIVE` |
| Pack version | `1.1.0` |
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

A cycle may end at a documented blocker or actionable escalation, but it must preserve work and a deterministic resume point.

## Operating invariants

- ProjectPipeline deterministic services own state transitions, readiness, resource admission, external-write intent, evidence evaluation, and completion.
- Models and agents are bounded workers or advisors, not canonical authorities.
- State required after restart lives outside chat.
- Every active implementation lane has one owner, work identity, branch, worktree, base SHA, resource claim set, and merge target.
- The same remote mutation has one idempotency identity and reconciliation path.
- Every sustained work period produces accepted progress, blocker reduction, valid evidence, corrected diagnosis, or scoped escalation.
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

## Autonomous decisions

Do not interrupt the operator for routine naming, internal structure, ordinary testing, or straightforward compatible fixes. Use plans, ADRs, policy, source, and professional judgment. Escalate only material decisions or actions that automation genuinely cannot perform.

## Completion boundary

The control projection may identify ready, active, blocked, or apparently completed work. The deterministic Completion Gate is the final authority for completion. See `12_TESTING_VERIFICATION_AND_COMPLETION.md`.
