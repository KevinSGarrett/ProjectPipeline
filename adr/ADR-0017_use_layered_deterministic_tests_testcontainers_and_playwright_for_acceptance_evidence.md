# ADR-0017 — Use layered deterministic tests, Testcontainers, and Playwright for acceptance evidence

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-009:L000013-L000017`, `SRC-016:L001800-L001807`, `GOV-001:L002066-L002103`
- **Date:** `2026-08-14`

## Context

Completion requires behavior-linked evidence across domain logic, database and adapter contracts, browser journeys, accessibility, security, failure, and recovery—not only unit tests or model self-review.

## Decision

Retain Python unittest for the dependency-free repository foundation. Add Testcontainers for real PostgreSQL and service integration contracts. Use Playwright Test as the authoritative browser functional and evidence-capture layer. Property, mutation, accessibility, load, and API-fuzz tools are enabled by risk profile rather than on every change.

## Alternatives considered

- Treat exploratory browser-agent output as final acceptance evidence.
- Mock every external dependency in integration tests.
- Run every expensive test class on every trivial documentation change.

## Consequences

Each acceptance criterion names its verification method. Browser traces, screenshots, database state, and fault results are evidence artifacts with hashes and provenance.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
