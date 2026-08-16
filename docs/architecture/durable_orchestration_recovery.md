# Durable Orchestration and Recovery

Project Pipeline separates **canonical workflow truth** from **durable-engine execution history**. Canonical workflow identity, idempotency, events, waits, checkpoints, worker leases/heartbeats, outbox state, and recovery decisions remain Project Pipeline-owned. Hatchet is the selected initial execution backend behind a stable port; DBOS and Temporal remain fallbacks.

## Upstream-first decision

The Pass 13 upstream gate reviewed all 18 mapped orchestration candidates before implementation. The decision retained Hatchet as the initial backend and mined Symphony, SWE-ReX, Worktrunk, container-use, and Bernstein where they add useful runner isolation, worktree ownership, environment isolation, replay, or audit patterns. Other multi-agent orchestration products remain references rather than additional authorities.

## Durable state flow

1. Register a versioned workflow definition.
2. Start with an idempotency key; the deterministic run identity prevents duplicate local creation.
3. Persist an external-operation record before any external backend mutation.
4. Emit ordered workflow events after canonical transitions.
5. Persist retries, waits, checkpoints, and worker heartbeats so restart does not erase progress.
6. Treat uncertain external mutation outcomes as reconciliation-required, not retryable failures.
7. Recover stale workers through fencing epochs and per-step retry/recoverability rules.

## Backend boundary

The Hatchet adapter uses the Python workflow runnable's nonblocking `run(..., wait_for_result=False)` boundary and records Project Pipeline idempotency metadata. Absence of `hatchet_sdk`, a runtime configuration, or credentials is reported explicitly. Local deterministic fault tests do not imply live Hatchet qualification.

Backend migration is deliberately conservative. A workflow with an established external run identity cannot be silently moved to another engine because doing so would split durable history and risk duplicate effects.

## Recovery invariants

- Unknown outcome means reconcile first.
- Fencing epochs reject stale workers.
- Retry attempts and backoff are bounded and persisted.
- Required checkpoints bind to a specific step attempt.
- Duplicate signals are accepted at most once by inbox identity.
- Timer waits use persisted UTC deadlines.
- Recovery decisions are durable evidence and distinguish safe automation from human/manual reconciliation.
