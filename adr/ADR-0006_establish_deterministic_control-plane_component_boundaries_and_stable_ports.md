# ADR-0006 — Establish deterministic control-plane component boundaries and stable ports

- **Status:** `ACCEPTED`
- **Source basis:** `GOV-001:L000362-L000793`, `SRC-003:L000040-L000083`, `SRC-014:L000013-L000086`
- **Date:** `2026-08-14`

## Context

Project Pipeline contains many named subsystems, but deterministic authority must remain distinguishable from advisory intelligence, execution backends, integrations, and operator surfaces.

## Decision

Model the product as a local-first modular control plane with explicit components, stable typed ports, declared state ownership, trust boundaries, and deployment profiles. The Project Control Kernel, policy, budget, resource, and completion gates own authoritative decisions. Advisory agents and optimization backends can recommend or execute only through those ports.

## Alternatives considered

- Treat every named capability as an independent network service immediately.
- Allow agent frameworks or workflow engines to own project truth.
- Use informal module coupling without machine-readable boundaries.

## Consequences

The architecture can be implemented incrementally without premature distributed-system burden. Registry and contract validation become mandatory whenever components or interfaces change.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
