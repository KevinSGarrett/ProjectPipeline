# Failure Recovery and Resumption

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-17` |
| Status | `ACTIVE` |
| Pack version | `1.1.0` |
| Primary domains | `failure_recovery`, `session_resumption` |
| Governing entry point | `AGENTS.md` |

## Recovery goals

Recover canonical state, preserved work, ownership, external effects, and next safe action after process loss, context compaction, laptop reboot, worker loss, network outage, provider failure, or repository inconsistency. Chat is never the recovery source.

## Rehydration inventory

A fresh session determines:

- repository identity and root;
- current branch, cleanliness, base SHA, and worktrees, or snapshot limitation;
- open PRs and check/review state when reachable;
- Jira in-progress, blocked, and ready work;
- latest control snapshot and last verified `main` SHA;
- active orchestration workflows, checkpoints, retries, outbox, and unknown outcomes;
- resource leases, fencing tokens, workers, and heartbeats;
- recent evidence and freshness;
- external-system health and pending writes;
- next eligible action.

Use `templates/SESSION_CHECKPOINT.md` and `scripts/instruction_cold_start.py`.

## Failure classification

Classify local implementation, dependency/tool, requirement/decision, security, credential, external provider, hardware, budget, resource conflict, stale generated state, benchmark input, unknown mutation outcome, split-brain, or corruption. The classification determines whether to retry, change strategy, reconcile, block, recover, or escalate.

## Unknown external outcome

Never retry first. Read external state, correlate intent/idempotency identity, reconcile, and retry only if effect is absent. Preserve pending intent in durable outbox/recovery state.

## Dirty or inconsistent Git state

Inspect changes and ownership, preserve meaningful work, checkpoint under an owned branch or artifact, reconcile worktrees/branches, then clean. Do not use destructive reset or clone proliferation.

## Provider outage

Enter `DEGRADED` or `LOCAL_FIRST` mode as policy directs. Record outage and pending mutations, stop repeated calls, continue local independent work, and reconcile before replay. Required live verification remains blocked.

## Split brain and stale workers

Fail closed. A valid witness/fencing decision is required before another controller commits canonical state. Expire/fence stale leases, inspect both sides, reconcile, and invalidate stale assumptions. Never accept two concurrent primary controllers.

## Backup and restore

Backup success is distinct from restore success. Follow domain RPO/RTO and tools in `config/resilience_policy.json`. Restoration occurs into an isolated target first, with integrity and functional verification, before promotion. Destructive restore requires explicit authority and rollback.

## Resume record

Record exact task, state, branch/worktree/SHA, changed files, tests, evidence, attempts/fingerprints, blockers, pending external intents, resource leases, next command, expected result, and stop conditions. A new session must be able to continue without interpreting chat.

## Global versus lane stop

Stop only the affected lane unless authority, security containment, split-brain, canonical corruption, or critical release integrity requires a global pause. Continue unaffected eligible work.
