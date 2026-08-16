# Work and Resource Claim

- Claim ID: `[CLAIM-ID]`
- Owning work item(s): `[PP-...]`
- Owner/worker: `[identity]`
- Risk: `[LOW / MEDIUM / HIGH / CRITICAL]`
- Branch: `[branch]`
- Worktree: `[path]`
- Base SHA: `[sha]`
- Merge target: `main`
- Start/expiry: `[timestamps]`

## Acceptance boundary

`[cohesive behavior and rollback unit]`

## Resource claims

| Kind | Resource | Mode | Reason |
|---|---|---|---|
| `[FILE/DIRECTORY/SCHEMA/DATABASE/PORT/ENVIRONMENT/REPOSITORY]` | `[identity]` | `[EXCLUSIVE/SHARED_READ]` | `[reason]` |

## Context receipt

- Instructions: `[paths/versions]`
- Jira source context: `[path]`
- Requirements/plans/ADRs: `[IDs]`
- Policies/contracts: `[paths]`
- Explicit exclusions: `[paths/classes]`

## Verification and evidence

- Targeted test: `[command]`
- Required merge tier: `[F/A/B/C/D/E/I]`
- Expected evidence: `[criterion and method]`

## External mutations

`[none, or action-intent/idempotency/authorization references]`

## Handoff and recovery

- Heartbeat/checkpoint: `[location]`
- Preserved-work method: `[method]`
- Next safe action after worker loss: `[action]`
