# Branch, Worktree, and Pull Request Policy

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-08` |
| Status | `ACTIVE` |
| Pack version | `1.1.0` |
| Primary domains | `branches`, `worktrees`, `pull_requests` |
| Governing entry point | `AGENTS.md` |

## Branch topology

Use protected `main`, short-lived work-item branches, and temporary integration, release, or hotfix branches only when justified. Accepted branch forms are encoded in `policies/BRANCH_PR_POLICY.json`.

Examples:

```text
feat/PP-TASK-000241-dynamic-lane-scheduler
fix/PP-BUG-000012-reconciliation-race
refactor/PP-TASK-000300-provider-boundary
test/PP-TASK-000333-golden-journeys
docs/PP-TASK-000210-runtime-handoff
chore/PP-TASK-000250-dependency-locks
hotfix/PP-BUG-000020-critical-regression
release/v1.0.0
```

Structural epics do not own implementation branches directly. Avoid random names and branch-per-command behavior.

## Worktree registration

Every active lane records:

- owning Jira item or cohesive item set;
- branch and worktree path;
- exact base SHA and merge target;
- owner/worker identity;
- resource claims for files, directories, schemas, databases, ports, environments, or repository scope;
- expected outputs and integration order;
- heartbeat or checkpoint state.

Use independent clones only for a genuine machine or trust-boundary need, and register them. Two machines never edit one mutable network-shared working tree concurrently.

## Resource claims

Claim the smallest safe resource set. Overlapping exclusive claims are denied or serialized. Shared generated artifacts, migrations, lock files, schemas, ports, and environment state require special coordination. A worker may not expand its claims silently.

## Dirty worktrees

Never automatically remove, reset, or overwrite a dirty worktree. Determine owner and intent; checkpoint or integrate the work; then clean. Stale age alone is not evidence that work is disposable.

## Pull request cohesion

One PR may satisfy multiple tasks when they form one functional slice, share acceptance, must be implemented together, have one rollback unit, and can be reviewed coherently. Split when domains, rollback, risk, or reviewer boundaries are materially independent.

Bad granularity separates a variable rename, its tests, regenerated index, and Jira traceability into different PRs. Good granularity integrates behavior, tests, generated output, documentation, traceability, and evidence in one reviewable change.

A PR that changes only one item's lifecycle or generated lifecycle projections is prohibited. An evidence-backed reconciliation-only PR must contain at least the batch size in `policies/BRANCH_PR_POLICY.json`; otherwise fold it into a real cohesive implementation slice or perform no PR-producing mutation. The delivery-progress gate evaluates the exact base and head and fails closed when this invariant is violated.

## PR content

Use `.github/pull_request_template.md` or `templates/PULL_REQUEST_BODY.md`. Include objective, Jira IDs, requirements, plans/ADRs, implementation summary, acceptance, tests/evidence, security/data/observability/operations impact, dependencies, external-system impact, rollback/recovery, UI evidence, known limitations, and follow-up.

Keep descriptions proportional to the change. Generated or docs-only changes do not need ceremonial essays.

## WIP limits

Start with no more than two implementation lanes. A third requires isolated workers, non-overlapping claims, known merge order, and adequate review throughput. Finish integration before opening more work.

## Branch cleanup proof

Cleanup requires all of:

- PR merged or intentionally closed with preserved work;
- merge SHA known;
- integrated-main checks complete for the risk tier;
- no owning worktree;
- no uncommitted or unpublished changes;
- Jira/evidence reconciliation complete;
- remote deletion authorized when requested.
