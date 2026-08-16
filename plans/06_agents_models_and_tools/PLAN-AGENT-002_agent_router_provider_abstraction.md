# PLAN-AGENT-002 — Agent Router and Provider/Tool Abstraction

- **Plan ID:** `PLAN-AGENT-002`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus required implementation detail
- **Source basis:** `SRC-001:L000569-L000680`, `SRC-001:L001302-L001372`, `SRC-006:L000011-L000282`, `SRC-009:L000019-L000021`, `SRC-013:L000046-L001054`, `SRC-017:L001002-L001064`, `GOV-001:L000456-L000470`, `GOV-001:L001560-L001573`

## PLAN-AGENT-002:SEC-01 Capability and identity registries

Capabilities are the first routing key. Providers, models, agents, and tools publish stable identity, versions, capabilities, constraints, execution mode, resource needs, cost behavior, authority class, and qualification state. Provider names never become project-task semantics.

## PLAN-AGENT-002:SEC-02 Provider-neutral task and result contracts

A universal execution task contract carries required capabilities, task class, risk, quality tier, bounded instructions/context, output schema, egress permission, and maximum-cost intent. Adapters translate that contract to provider protocols and normalize output, usage, request identity, finish state, and errors.

## PLAN-AGENT-002:SEC-03 Qualification and version quarantine

New model, tool, and adapter versions begin quarantined. Production eligibility requires standardized health, execution, cancellation, usage, timeout, malformed-output, quota, checkpoint, and context-acknowledgement checks plus rollback readiness. Shadow and canary states remain distinct from full qualification.

## PLAN-AGENT-002:SEC-04 Capability-first routing and fallback policy

Routing first removes targets that do not satisfy every required capability. It then applies qualification, provider runtime state, circuit state, egress, quality, and policy constraints before deterministic scoring. Preferred and fallback provider order is configuration, not project meaning.

## PLAN-AGENT-002:SEC-05 Provider runtime state and circuit breakers

Providers expose healthy, degraded, rate-limited, quota-low, budget-exhausted, authentication-failed, unavailable, disabled, maintenance, and recovery observations. Transient repeated failures open a bounded circuit; after cooldown a controlled half-open probe may recover it. Disabled or authorization-failed providers are not blindly retried.

## PLAN-AGENT-002:SEC-06 Performance and verified-outcome registry

Per target and capability, the platform records success, latency, normalized cost when known, retries, rework, review findings, and quality evidence. Routing may consume this evidence but cannot fabricate samples or make unqualified versions eligible.

## PLAN-AGENT-002:SEC-07 Local and hosted model abstraction

Local processes and hosted APIs implement the same internal provider port. Local execution remains first-class for privacy, outage, or budget pressure, but local models do not acquire deterministic project-control authority. GPU-bound local execution still requires scheduler leases and measured capacity.

## PLAN-AGENT-002:SEC-08 Tool adapter boundary

Tools use stable adapter identity, capability registration, qualification, and explicit operation allowlists. Mutating tool use remains subject to action intent, policy, credential, and later security controls; the model or tool cannot grant itself authority.

## PLAN-AGENT-002:SEC-09 Persistence, observability, and simulation

Registry snapshots, provider observations, circuit state, performance observations, qualification reports, routing decisions, and execution receipts are persistent, queryable records. Deterministic simulations verify provider failure, fallback, circuit opening, and recovery without claiming live external behavior.

## PLAN-AGENT-002:SEC-10 Current verification boundary

The deterministic router, registries, circuit breaker, mock/local adapters, HTTP protocol adapters, persistence, CLI, schemas, and simulations are locally verifiable. Hosted-provider credentials, real model qualification, LiteLLM activation, Pydantic AI activation, monetary-budget coupling, and production worker orchestration remain separately gated or downstream.
