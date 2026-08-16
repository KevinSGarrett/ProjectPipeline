# ADR-0012 — Use OPA and Conftest for policy and SOPS plus age for local encrypted configuration

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-009:L000007-L000009`, `SRC-014:L000175-L000230`, `SRC-016:L001784-L001787`, `SRC-016:L002201-L002209`
- **Date:** `2026-08-14`

## Context

Policy, authorization, egress, spending, deployment, and completion rules must be explicit and testable. Local operation also needs encrypted configuration without distributing permanent plaintext secrets to agents.

## Decision

Use OPA/Rego as the runtime policy decision engine and Conftest for repository, configuration, and infrastructure policy tests. Use SOPS with age recipients for the local encrypted configuration baseline. Keep secret values outside context packs and logs. OpenBao remains an optional advanced broker profile for dynamic secrets, leases, and larger deployments.

## Alternatives considered

- Scatter authorization conditionals across application code.
- Store all provider credentials in a shared plaintext environment file.
- Require OpenBao for every local installation.

## Consequences

Application services remain the policy enforcement points. SOPS and OpenBao licensing obligations are recorded separately. Secret-broker interfaces must support later AWS KMS or managed integrations without exposing raw master credentials.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
