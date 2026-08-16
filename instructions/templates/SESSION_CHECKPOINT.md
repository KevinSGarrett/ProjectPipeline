# Autonomous Session Checkpoint

- Checkpoint ID: `[CHECKPOINT-ID]`
- Timestamp UTC: `[timestamp]`
- Project/root: `ProjectPipeline / [root]`
- Git state: `[branch, SHA, cleanliness, worktrees, or SNAPSHOT_NOT_GIT_CHECKOUT]`
- Last verified main SHA: `[sha or unknown]`

## Preflight

| Check | Result | Evidence |
|---|---|---|
| Doctor | `[result]` | `[path/output digest]` |
| Repository validation | `[result]` | `[path/output digest]` |
| Jira validation | `[result]` | `[counts/path]` |
| Instruction validation | `[result]` | `[path/output digest]` |
| Control evaluation/sequence | `[state/ready count]` | `[snapshot IDs]` |

## Current lane

- Work item/acceptance: `[identity]`
- Branch/worktree/base: `[identity]`
- Resource claims: `[claims]`
- Changed files: `[paths]`
- Test/evidence state: `[state]`
- Attempts/fingerprints: `[records]`

## External and worker state

- Open PR/checks: `[state]`
- Jira reconciliation: `[state]`
- Pending writes/unknown outcomes: `[state]`
- Workers/heartbeats/leases: `[state]`
- Provider health: `[state]`

## Next safe action

`[exact action/command and expected result]`

## Stop/escalation conditions

`[conditions]`
