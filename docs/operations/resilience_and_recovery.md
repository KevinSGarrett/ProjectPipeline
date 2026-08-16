# Resilience and Recovery

Project Pipeline treats resilience as deterministic control behavior rather than a model decision. The Recovery Director evaluates failure domains, chooses an explicit operating mode, fences control-machine failover, preserves unaffected work, and requires reconciliation before restored authority can commit.

## Operating modes

- `FULL`: all qualified capabilities are available.
- `DEGRADED`: one or more replaceable capabilities are unavailable; unaffected deterministic work continues.
- `LOCAL_FIRST`: remote network or cloud dependencies are unavailable; local control, workers, repository state, evidence, and local model assistance remain available where qualified.
- `RECOVERY`: canonical state is unavailable or unsafe; only read, restore, reconcile, and notification paths remain eligible.
- `PAUSED`: operator/policy pause with state preserved.
- `EMERGENCY_STOP`: mutating execution is stopped; evidence and notification remain available.

## Authority and split-brain prevention

A standby may assume control only after the active authority lease is expired or fenced and an independent witness confirms takeover. Fencing tokens are monotonic. The candidate reconciles canonical state before committing. A model runtime, cloud burst worker, or backup tool never issues control authority.

## Local intelligence

The provider-neutral local gateway supports Ollama, llama.cpp server, and an optional llama-swap layer. These runtimes are advisory only. They may provide triage, summarization, review support, routing assistance, and outage fallback but cannot make authoritative project-state transitions.

## Backup and restore

PostgreSQL-specific backup is planned through pgBackRest; portable encrypted repository/artifact protection is planned through restic. A successful backup is not a successful recovery claim. Restore verification must occur in an isolated target and must record integrity checks plus observed recovery time/point before a production-readiness claim is allowed.

## Optional AWS cloud spine

AWS is an optional support plane: witness, durable ingress/queueing, backup/event ledger, watchdog, observability, budget controls, and bounded recovery. The default profile remains local-primary. Cloud removal or outage must not corrupt local project state. Infrastructure is represented as IaC but is not applied automatically.
