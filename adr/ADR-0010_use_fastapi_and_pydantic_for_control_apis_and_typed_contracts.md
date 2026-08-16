# ADR-0010 — Use FastAPI and Pydantic for control APIs and typed contracts

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-010:L001338-L001352`, `GOV-001:L001219-L001285`
- **Date:** `2026-08-14`

## Context

The control plane needs locally executable APIs, strict validation, generated schemas, async integration support, and clear contracts usable by Python services, the operator application, tests, and autonomous workers.

## Decision

Use Python 3.11 or newer, Pydantic models for boundary validation, and FastAPI for HTTP and streaming control APIs. Domain code remains framework-independent; FastAPI routes translate transport models to application commands and queries.

## Alternatives considered

- Expose unvalidated dictionaries as the primary contract.
- Couple domain entities directly to an HTTP framework.
- Introduce polyglot services before workload evidence justifies them.

## Consequences

OpenAPI and JSON Schema become generated interface artifacts. Transport compatibility tests are required before contract changes are accepted.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
