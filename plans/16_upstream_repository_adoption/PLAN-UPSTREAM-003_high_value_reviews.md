# PLAN-UPSTREAM-003 — High-Value Upstream Review Results

- **Plan ID:** `PLAN-UPSTREAM-003`
- **Status:** `ACTIVE`
- **Authority:** canonical source chronology plus official upstream evidence interpreted under Project Pipeline requirements
- **Source basis:** `GOV-001:L000797-L000876`, `SRC-011:L001212-L001345`, `SRC-016:L001691-L001832`, `SRC-016:L002197-L002303`

## PLAN-UPSTREAM-003:SEC-01 Durable execution

The later canonical architecture supersedes earlier candidate ordering: Hatchet is the initial direct-use backend behind DurableExecutionPort. Temporal and DBOS remain qualified fallback and benchmark adapters. No workflow backend owns authoritative project state, completion, or evidence.

## PLAN-UPSTREAM-003:SEC-02 Graph, scheduling, and retrieval

NetworkX is selected for dependency, conflict, ownership, resource, and critical-path analysis. OR-Tools is selected as a bounded lane optimizer whose output is revalidated against canonical constraints. PostgreSQL plus pgvector is the default semantic retrieval boundary; standalone vector services remain profile-gated.

## PLAN-UPSTREAM-003:SEC-03 Policy and secrets

OPA is selected for runtime decisions and Conftest for Rego-based configuration and infrastructure preflight. SOPS with age is selected for encrypted local configuration. OpenBao remains a later optional dynamic-secrets profile.

## PLAN-UPSTREAM-003:SEC-04 Agents, providers, and tools

Pydantic AI is selected for typed advisory agents. Docker MCP Gateway is selected for the first governed MCP lifecycle boundary; Context Forge remains later-only federation. LiteLLM remains a source-selected target behind a provider port, but activation is blocked pending license and public release-channel approval. Official provider protocols remain preferred where available.

## PLAN-UPSTREAM-003:SEC-05 Observability and operator delivery

OpenTelemetry and OTLP are the portable telemetry contract, with OpenLIT selected for agent/model instrumentation. React provides the network client; AG-UI is a compatibility adapter; Tauri official plugins provide bounded Windows desktop features; WinSW supervises eligible Windows-native services.

## PLAN-UPSTREAM-003:SEC-06 Verification

Playwright is selected for browser acceptance, accessibility, visual, and evidence capture. Testcontainers provisions real transient dependencies. Both produce evidence consumed by Project Pipeline's Completion Gate and do not define completion themselves.

## PLAN-UPSTREAM-003:SEC-07 Activation and fallback discipline

A source-selected technology is still inactive until pinned provenance, license classification, security review, configuration, compatibility tests, recovery, upgrade, and rollback evidence exist. Activation-blocked targets preserve architectural intent without pretending the external gate is complete.
