# ADR-0015 — Use Docker MCP Gateway behind an internal governed tool port

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-014:L000210-L000230`, `SRC-016:L001778-L001783`, `SRC-016:L002249-L002255`
- **Date:** `2026-08-14`

## Context

Autonomous workers need controlled access to tools and external systems, with registration, allowlists, isolation, identity, secrets, telemetry, and revocation.

## Decision

Use Docker MCP Gateway as the initial MCP lifecycle and isolation implementation behind Project Pipeline's GovernedToolPort. The internal registry remains authoritative for tool identity, capability, policy, and audit. Official GitHub and Atlassian integrations are attached through governed adapters; no MCP server receives ambient host authority by default.

## Alternatives considered

- Connect every agent directly to ungoverned MCP servers.
- Make one MCP vendor's catalog the authoritative capability registry.
- Expose host environment secrets directly to tool processes.

## Consequences

Docker availability is a deployment prerequisite for this profile. A direct adapter may exist for critical systems, but must pass the same action-intent and policy contracts.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
