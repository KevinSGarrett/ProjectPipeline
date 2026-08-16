# PLAN-ARCH-002 — Component Boundaries and State Ownership

- **Plan ID:** `PLAN-ARCH-002`
- **Status:** `ACTIVE`
- **Authority:** source-derived architecture constraints and required implementation detail
- **Source basis:** `SRC-003:L000852-L001000`, `SRC-006:L002748-L002818`, `SRC-017:L000281-L000358`

## PLAN-ARCH-002:SEC-01 Component catalog

Every responsibility has a stable component ID, layer, authority statement, source and requirement links, accepted decisions, dependencies, and provided or consumed interfaces. Components without runtime implementation remain explicitly `PLANNED_ONLY`; empty source scaffolds do not represent progress.

## PLAN-ARCH-002:SEC-02 State ownership

Each canonical entity has one authoritative owner. Other components may hold projections, caches, workflow history, or external mirrors, but they reconcile through that owner. PostgreSQL-backed domain services own durable operational metadata; Git owns repository revisions; immutable artifacts are digest addressed; Jira and provider state require reconciliation.

## PLAN-ARCH-002:SEC-03 Trust boundaries

Operator input, probabilistic intelligence, worker execution, external systems, canonical state, and network deployment are separate trust boundaries. Each crossing requires typed schemas, identity, policy, least privilege, timeouts, audit correlation, and content handling appropriate to the data classification.

## PLAN-ARCH-002:SEC-04 Stable internal ports

Durable execution, providers, tools, policy, artifacts, telemetry, repositories, and work-management behavior use stable internal ports. Adapters translate vendor behavior into Project Pipeline contracts. Vendor SDK objects do not cross into domain state or determine completion.

## PLAN-ARCH-002:SEC-05 Command and event model

A command requests an authoritative transition and carries actor, intent, scope, target, correlation, and idempotency information. A domain event records a committed fact. Transactional inbox and outbox records make external delivery recoverable. Unknown outcomes remain unresolved until reconciliation proves the result.

## PLAN-ARCH-002:SEC-06 Evidence and completion boundary

Execution output is a candidate result until acceptance criteria and required evidence are verified. The Completion Gate consumes stable evidence identities and freshness, not model confidence, worker self-report, Jira status, or user-interface projection alone.

## PLAN-ARCH-002:SEC-07 Dependency direction

Operator surfaces depend on application APIs; application services invoke deterministic domain services; domain services depend on ports; adapters implement ports; persistence and telemetry are infrastructure. Reverse dependencies into vendor SDKs or user-interface state are prohibited.
