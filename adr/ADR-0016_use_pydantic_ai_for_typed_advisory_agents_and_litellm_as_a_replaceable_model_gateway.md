# ADR-0016 — Use Pydantic AI for typed advisory agents and retain LiteLLM behind a replaceable, activation-gated model gateway port

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-011:L000654-L000722`, `SRC-016:L001788-L001792`
- **Date:** `2026-08-14`

## Context

Advisory agents need typed outputs, tool contracts, provider portability, cost/telemetry normalization, and explicit separation from deterministic authority.

## Decision

Use Pydantic AI behind the internal advisory-agent and provider ports. Preserve LiteLLM as the source-selected replaceable multi-provider gateway target, but mark activation blocked because the inspected upstream snapshot has unasserted licensing and an unsuitable default release channel. Direct official provider adapters remain valid and preferred where they offer stronger protocol fidelity. No framework may own project truth, completion, or authorization.

## Alternatives considered

- Let an agent framework own orchestration and completion.
- Use one provider SDK throughout domain code.
- Activate LiteLLM without resolving current license and release-channel evidence.

## Consequences

Pydantic AI can be activated after version, structured-output, tool-policy, and portability tests. LiteLLM remains uninstalled and non-activatable until explicit human approval and a pinned public release pass licensing, security, provider-contract, cost, fallback, telemetry, and rollback gates.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, source evolution, or measured workload characteristics invalidate its assumptions.
