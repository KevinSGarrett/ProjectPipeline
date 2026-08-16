# Parallel Agent Coordination

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-10` |
| Status | `ACTIVE` |
| Pack version | `1.0.1` |
| Primary domains | `parallel_execution`, `observability` |
| Governing entry point | `AGENTS.md` |

## Controlled parallelism

Parallel work is allowed only when the dependency graph, resource claims, workspace isolation, ports/services, migrations, generated artifacts, and merge order are compatible. The objective is throughput without integration failure, not maximum worker count.

Project Control establishes readiness. Dynamic Lane Scheduler admits compatible work and owns resource leases/fencing. Durable orchestration owns workflow checkpoints, retries, heartbeats, cancellation, and recovery. Do not create a second agent spreadsheet or ad hoc lock file.

## Lane admission

A lane request includes task ID, branch, worktree, base SHA, owner, requested resources, environment, expected duration, risk, budget, merge target, and dependencies. Scheduler either admits the complete atomic claim or denies it; partial claim admission is unsafe.

Exclusive conflict examples include the same source file, migration catalog, lockfile, schema, shared generated registry, database, port, environment, or release artifact. Read-only exploration can share resources when no mutation or sensitive data conflict exists.

## Roles and independence

Use explorer, implementer, verification, security, integration, and release roles when needed. For high-risk work, the reviewer or verification worker must not simply restate the implementer's conclusion. Independence is demonstrated by separate evidence method, worker identity, or review boundary required by assurance policy.

## Handoffs

Every handoff contains task/acceptance, current branch/worktree/base, changed files, resource claims, test status, evidence, blockers, assumptions, external effects, next safe action, and stop conditions. Persist it in project state or a checkpoint artifact, not chat alone.

## Heartbeats and fencing

Workers maintain bounded heartbeat state. A missing heartbeat does not immediately authorize reassignment; the controlling system expires or fences the lease, inspects workspace/remote state, reconciles unknown effects, and only then reassigns. A stale worker cannot later commit canonical state with an old fencing token.

## Observability

Use structured records with project/task/correlation IDs, worker, operation, result, retry count, blocker, resource lease, cost, and evidence references. Redact secrets and sensitive data. Avoid enormous raw prompt logs unless required, approved, and safely redacted.

## Shared generated artifacts

When multiple tasks affect one generated registry, serialize generation or designate an integration owner. Workers change authoritative inputs and return narrow artifacts; the integration lane regenerates once after accepted inputs converge. Avoid noisy full-repository regeneration on every lane.

## Parallel failure containment

A blocked lane preserves work, releases only safe claims, and records exact blocker and resume conditions. Other independent lanes continue. A global stop is reserved for global authority, security, split-brain, corruption, or release-integrity failure.

## Multi-machine rules

Each machine uses an independent clone or worktree, explicit branch ownership, Git/artifact transfer, and resource leases. Never edit one shared mutable network tree from both machines. See `16_REMOTE_MACHINE_AND_RESOURCE_PROTOCOL.md`.
