# ADR-0005 — Start with a modular monolith for deterministic control

- **Status:** `ACCEPTED`
- **Source basis:** `GOV-001:L000362-L000793`, `GOV-001:L002235-L002271`
- **Date:** `2026-08-14`

## Context

Project Pipeline has many named responsibilities, but premature service separation would multiply deployment, consistency, credential, recovery, and debugging burden before workload evidence exists.

## Decision

Use a local-first modular control plane with strict internal packages, typed ports, declared state ownership, and machine-readable component boundaries. Extract an independently deployed service only when measured scale, security isolation, failure isolation, independent release cadence, or availability evidence justifies the added operational cost.

## Alternatives considered

- Immediate service decomposition was rejected because it would introduce distributed consistency and operating burden before a verified vertical slice exists.
- A single unbounded module was rejected because it would obscure authority, testing, and future extraction boundaries.
- A provider-framework-owned control plane was rejected because unique Project Pipeline truth and completion semantics must remain internal.

## Consequences

The first implementation remains auditable and transactional. Package dependency direction, interfaces, state ownership, and trust boundaries are validated. Any service extraction requires a separate ADR and compatibility evidence.

## Review trigger

Revisit when measured performance, isolation, release, or resilience requirements cannot be met inside the modular control plane.
