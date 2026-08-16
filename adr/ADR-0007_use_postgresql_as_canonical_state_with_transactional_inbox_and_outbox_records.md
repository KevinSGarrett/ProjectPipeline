# ADR-0007 — Use PostgreSQL as canonical state with transactional inbox and outbox records

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-003:L000962-L001000`, `SRC-009:L000019-L000020`, `SRC-016:L002201-L002230`
- **Date:** `2026-08-14`

## Context

Project state, work state, evidence metadata, policy decisions, leases, costs, incidents, and synchronization outcomes require transactions, constraints, migrations, backup, and deterministic reconciliation.

## Decision

Use PostgreSQL as the authoritative operational store. Domain state changes that publish work or integration events must atomically persist outbox records; inbound externally observed operations must use inbox/idempotency records before effects are accepted. Workflow-engine state and user-interface projections are not canonical domain truth.

## Alternatives considered

- Use workflow-engine history as the only database.
- Use independent SQLite files as the primary multi-process store.
- Use an event broker without a transactional source of truth.

## Consequences

Local development may run PostgreSQL in a container. AWS operation may use a managed PostgreSQL-compatible service. A portable offline profile may use a constrained adapter only after conformance tests prove compatible semantics.

The repository includes an executable SQLite local profile behind the persistence port. It is a deterministic development and verification projection, not a replacement for PostgreSQL production authority. Its state, migration, optimistic-concurrency, and traceability semantics are contract-tested, while live PostgreSQL activation remains gated by migration, backup, restore, and integration evidence.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
