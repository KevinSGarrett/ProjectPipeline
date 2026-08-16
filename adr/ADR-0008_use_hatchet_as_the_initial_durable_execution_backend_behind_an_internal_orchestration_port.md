# ADR-0008 — Use Hatchet as the initial durable execution backend behind an internal orchestration port

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-011:L000102-L000184`, `SRC-016:L001752-L001756`, `SRC-016:L002223-L002230`
- **Date:** `2026-08-14`

## Context

Long-running autonomous work must survive process loss, retries, human pauses, unknown external outcomes, and provider failure without transferring Project Pipeline authority into a vendor-specific workflow history.

## Decision

Keep Project Pipeline workflow identities, state transitions, idempotency, evidence, and reconciliation in internal contracts and PostgreSQL. Select self-hosted Hatchet as the initial DurableExecutionPort backend because the latest canonical source explicitly places Hatchet in direct use and DBOS, Temporal, and Restate in benchmark/fallback roles. Retain Temporal and DBOS as qualified fallback adapters, not co-equal active engines.

## Alternatives considered

- Make Temporal the mandatory baseline despite the later source revision.
- Make DBOS the initial baseline because of its compact PostgreSQL-centered library model.
- Build a custom durable engine before validating a complete vertical slice.

## Consequences

Hatchet-specific SDK types cannot cross DurableExecutionPort. Before live autonomous use, conformance and fault-injection tests must verify retries, cancellation, checkpoints, restart recovery, unknown-outcome reconciliation, and human-required pauses. Fallback migration must preserve Project Pipeline identities and canonical state.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, source evolution, or measured workload characteristics invalidate its assumptions.
