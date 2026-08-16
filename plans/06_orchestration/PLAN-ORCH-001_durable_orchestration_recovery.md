# PLAN-ORCH-001 — Durable Orchestration and Recovery

- **Plan ID:** `PLAN-ORCH-001`
- **Status:** `ACTIVE`
- **Authority:** deterministic Project Pipeline workflow contracts, source-derived recovery requirements, ADR-0008, and the permanent Upstream Adoption Gate
- **Source basis:** `SRC-003:L000040-L000083`, `SRC-003:L000882-L001001`, `SRC-005:L000604-L000735`, `SRC-006:L000283-L000405`, `SRC-006:L000442-L000518`, `SRC-017:L000281-L000359`, `SRC-016:L001748-L001756`

## PLAN-ORCH-001:SEC-01 Upstream-first durable-runtime gate

Pass 13 evaluates the complete governed orchestration candidate set before material implementation. Hatchet remains the selected initial durable backend behind `DurableExecutionPort`; DBOS and Temporal remain qualified fallbacks rather than co-equal authorities. OpenAI Symphony contributes orchestrator/runner separation and live-fault testing patterns, SWE-ReX contributes execution-runtime isolation, Worktrunk remains the repository/worktree boundary, and Bernstein contributes deterministic replay and tamper-evident lineage patterns. Overlapping agent fleet and worktree products remain comparative references to avoid introducing a second Project Control Kernel.

## PLAN-ORCH-001:SEC-02 Canonical workflow identity and state ownership

Project Pipeline owns workflow definition identity, workflow run identity, state, version, idempotency identity, current step/attempt, waits, checkpoints, worker assignment, retry schedule, failure state, and recovery count. External durable engines own execution-specific history only. Canonical workflow IDs are deterministic from definition plus idempotency key. Optimistic row versions prevent stale control writers from silently replacing newer workflow state.

## PLAN-ORCH-001:SEC-03 Durable events, inbox, outbox, and uncertain outcomes

Every workflow transition emits a stable ordered event. Incoming signals are deduplicated by immutable message identity before they can alter workflow state. External mutations are persisted in the outbox before transmission and progress through explicit pending, sent, acknowledged, unknown-outcome, reconciled, or failed states. A response loss after a remote mutation is never converted into a blind retry; it requires reconciliation of the remote effect first.

## PLAN-ORCH-001:SEC-04 Retry, backoff, timeout, and checkpoint semantics

Steps carry bounded retry policy, deterministic exponential backoff, execution timeout, schedule timeout, recoverability, and checkpoint requirements. Failure may schedule another attempt only while retry policy permits it. Required checkpoints are content-addressed and bound to the current step and attempt. Step success cannot bypass a required checkpoint. Retry availability is persisted as an absolute UTC instant so process restart does not reset the delay.

## PLAN-ORCH-001:SEC-05 Durable signal and timer waits

Signal and timer waits are first-class persisted records. A signal wait resumes only for the declared signal and its inbox delivery is idempotent. Timer waits survive process restart and are released from persisted UTC deadlines. Wait identity is semantic rather than process-local, allowing a restarted runtime to recover the same waiting workflow without replaying prior side effects.

## PLAN-ORCH-001:SEC-06 Worker heartbeat, fencing, and loss recovery

Workers publish expiring heartbeats with monotonic fencing epochs. Assignment rejects stale fencing epochs. Recovery scans expired workers and evaluates each affected workflow independently. Recoverable steps with remaining attempts are converted into bounded retry schedules; nonrecoverable or ambiguous work becomes `RECOVERY_REQUIRED` for controlled reconciliation. Unaffected workflows continue independently.

## PLAN-ORCH-001:SEC-07 Backend adapters and failover boundary

The Hatchet adapter maps Project Pipeline workflow starts to Hatchet's nonblocking workflow trigger boundary while preserving Project Pipeline idempotency metadata. The adapter truthfully reports dependency/configuration state and is not labeled live verified without a configured runtime. DBOS and Temporal adapters remain explicit fail-closed fallback/conformance targets until separately qualified. Active external workflow histories cannot silently migrate to another backend; fallback is allowed only through an explicit migration/failover decision when history safety is proven.

## PLAN-ORCH-001:SEC-08 Persistence and PPDB-0010

`PPDB-0010_durable_orchestration_recovery` adds reversible SQLite and PostgreSQL-oriented tables for definitions, workflows, events, checkpoints, waits, workers, inbox, outbox, and recovery decisions. Local SQLite behavior, optimistic concurrency, restart persistence, and rollback are tested in this pass. PostgreSQL DDL is implementation-complete but remains not live-server-qualified.

## PLAN-ORCH-001:SEC-09 CLI, schemas, simulations, and operations

The CLI exposes machine-readable orchestration status, backend qualification status, definition registration, workflow start/query, signal, checkpoint, heartbeat, recovery, cancellation, resume, and deterministic fault simulations. Local state mutation requires explicit apply and approval flags. Generated schemas cover workflow definitions/runs/events, operations, retries, waits, checkpoints, heartbeats, recovery decisions, backend capabilities/receipts/observations, policy, status, signals, and simulations. Operational recovery is documented in a dedicated runbook.

## PLAN-ORCH-001:SEC-10 Verification and truth boundary

Pass 13 verification covers deterministic identity, idempotent starts and signals, optimistic concurrency, retry exhaustion/backoff, checkpoint gates, restart-safe waits, fencing epochs, stale-worker recovery, unknown remote outcomes, mock response loss, failover prohibition, backend capability truth, migration rollback, CLI behavior, schemas, provenance, Jira/traceability, and cumulative regression. The Durable Workflow Runtime advances to `PARTIALLY_IMPLEMENTED`: Project Pipeline's local durability/recovery semantics and backend boundaries are real, while a live Hatchet control plane, production PostgreSQL, distributed workers, and separately qualified DBOS/Temporal fallback deployments remain external or later-pass work.
