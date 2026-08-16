# ADR-0004 — Deny external mutation by default

- **Status:** `ACCEPTED`
- **Source basis:** `GOV-001:L001389-L001415`, `GOV-001:L002184-L002196`
- **Date:** `2026-08-14`


## Context

The platform will eventually interact with GitHub, Jira, cloud resources, providers, and operator systems. Accidental or unaudited mutation is a high-impact failure mode.

## Decision

All external mutation is denied unless a typed action intent identifies actor, target, operation, scope, authorization, and idempotency identity and policy explicitly permits it.

## Alternatives considered

- Allow writes after credential discovery
- Per-adapter permissive defaults
- Deny by default with explicit authorization

## Consequences

Read, simulation, mock, and dry-run work can proceed safely. Live adapters must implement the same contract before activation.

## Review trigger

Revisit when measured project constraints, security findings, or operational evidence invalidate this decision.
