# PLAN-AGENT-001 — Agents, Models, Providers, and Tools

- **Plan ID:** `PLAN-AGENT-001`
- **Status:** `PARTIALLY_IMPLEMENTED`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000457-L000470`, `GOV-001:L001560-L001573`, `SRC-014:L000001-L000115`

## PLAN-AGENT-001:SEC-01 Capability-first routing

Workers, models, providers, and tools are registered by capabilities, limitations, versions, cost, latency, reliability, privacy, and qualified environments. Routing starts from task requirements rather than a preferred provider name.

## PLAN-AGENT-001:SEC-02 Adapter boundary

Provider and tool integrations implement stable internal contracts. Adapters normalize request, response, error, usage, and audit semantics while preserving provider-specific evidence. Internal control semantics remain owned by Project Pipeline.

## PLAN-AGENT-001:SEC-03 Qualification

A model or tool version is not production-eligible solely because it responds. Qualification uses representative tasks, expected outputs, safety constraints, latency, cost, failure behavior, and regression comparison. Qualification expires when relevant versions or contracts change.

## PLAN-AGENT-001:SEC-04 Fallback and circuit breaking

Routing supports ordered fallbacks that respect capability, privacy, budget, and authorization. Circuit breakers prevent repeated use of an unhealthy provider. A fallback may reduce capability but cannot bypass acceptance or security requirements.

## PLAN-AGENT-001:SEC-05 Local and hosted execution

Local models are first-class advisory providers behind a neutral gateway. Ollama is the initial local-service candidate, llama.cpp a direct-serving fallback, and llama-swap an optional multi-model gateway; each remains unqualified until a pinned target runtime passes profile-specific checks. Local models may support triage, summarization, Jira hygiene, review support, routing assistance, and outage fallback but cannot replace deterministic control authority. Hosted providers remain optional and replaceable.
