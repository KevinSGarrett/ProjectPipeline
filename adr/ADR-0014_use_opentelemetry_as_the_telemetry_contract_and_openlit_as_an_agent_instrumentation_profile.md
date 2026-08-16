# ADR-0014 — Use OpenTelemetry as the telemetry contract and OpenLIT as an agent instrumentation profile

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-016:L001792-L001794`, `SRC-016:L002272-L002276`, `GOV-001:L000696-L000710`
- **Date:** `2026-08-14`

## Context

Logs, metrics, traces, costs, model calls, workflows, and evidence need shared correlation identities without locking core services to one observability product.

## Decision

Use OpenTelemetry semantic conventions and OTLP as the primary instrumentation/export contract. Add OpenLIT SDK instrumentation for supported model and agent workloads, routed through an OpenTelemetry Collector. Prometheus-compatible metrics and Windows host metrics are deployment-profile choices, not hard-coded domain dependencies.

## Alternatives considered

- Adopt a single hosted telemetry vendor as a mandatory dependency.
- Use unstructured logs as the only observability source.
- Let observability products determine domain health semantics.

## Consequences

Health remains deterministically computed by Project Pipeline from observed facts. Telemetry backends can be replaced while preserving correlation and audit identities.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
