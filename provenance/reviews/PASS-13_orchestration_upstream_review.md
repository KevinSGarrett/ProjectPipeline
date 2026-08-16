# Pass 13 Orchestration Upstream Review

## Decision

Material durable-orchestration implementation is permitted only after this review. Project Pipeline retains canonical workflow identity, project state, recovery decisions, inbox/outbox state, and authority semantics behind a stable `DurableExecutionPort`. No upstream orchestrator may become a second project-control authority.

## Runtime baseline and fallbacks

- **UPSTREAM-050 — Hatchet**: selected initial durable runtime backend. Source inspection confirmed Python workflow/task configuration supports execution and schedule timeouts, retries, backoff settings, concurrency and idempotency. Integration must remain behind Project Pipeline's port and is not live-qualified without an installed/configured Hatchet runtime.
- **UPSTREAM-026 — DBOS**: retained as a qualified fallback/conformance target. Source inspection confirmed workflow registration/start, queues, recorded sleep, event/message primitives, scheduler support and pending-workflow recovery. It does not replace the initial Hatchet choice.
- **UPSTREAM-104 — Temporal**: retained as a qualified fallback/conformance target for durable history, timers/signals and worker recovery semantics. Activation requires a separately qualified Temporal deployment.

## Adopted implementation and architecture patterns

- **UPSTREAM-074 — OpenAI Symphony**: mine orchestrator/agent-runner separation plus live fault/E2E testing patterns.
- **UPSTREAM-102 — SWE-ReX**: use the already implemented execution-runtime/deployment isolation boundary; do not make it canonical workflow state.
- **UPSTREAM-095 — Bernstein**: mine deterministic replay, lineage, offline-verifiable audit and fail-closed containment patterns. Do not adopt it as a second orchestrator.
- **UPSTREAM-061 — Worktrunk**: preserve the existing Repository Steward worktree boundary; durable orchestration consumes that boundary rather than replacing it.
- **UPSTREAM-025 — container-use**: retain as a future execution-environment/sandbox reference behind the worker runtime boundary, not as the durable workflow engine.

## Comparative references not adopted as baseline control planes

AgentsMesh, agetor, groundcrew, CAS, Overstory, Parallel Code, Workmux, Claude Squad, Conflux and agent-orchestrator all provide useful fleet/worktree/agent-management patterns, but materially overlap Project Pipeline's existing Control Kernel, Dynamic Lane Scheduler, Repository Steward and Agent Router. Importing them as additional orchestrators would create duplicate authority. Overstory is archived. Claude Squad is AGPL-3.0-only. Current GitHub metadata does not establish an activation-safe license for Conflux, and AgentsMesh is not activation-eligible under the current license review.

## Pass 13 implementation contract

1. Canonical workflow semantics remain Project Pipeline-owned.
2. Hatchet is the initial backend adapter, not the authority database.
3. Active workflow histories are never silently migrated between durable backends.
4. Unknown external mutation outcomes are reconciled before retry.
5. Worker loss, retry, waits and recovery are deterministically testable without a live external backend.
6. DBOS and Temporal remain fallback adapters/conformance targets until separately qualified.
7. External runtime absence must not prevent local implementation, mocks, migrations, fault tests, CLI, traceability or evidence.
