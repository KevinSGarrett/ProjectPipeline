# PLAN-CTX-001 — Context and Knowledge Architecture

- **Plan ID:** `PLAN-CTX-001`
- **Status:** `PLANNED`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `SRC-002:L001015-L001156`, `GOV-001:L000472-L000485`, `GOV-001:L001575-L001588`


## PLAN-CTX-001:SEC-01 Context policy

No delegated work starts without an explicit context envelope. Context is purpose-specific, minimal, source-grounded, versioned, and auditable. More context is not automatically better; irrelevant or untrusted material increases risk.

## PLAN-CTX-001:SEC-02 Context Broker

The Context Broker resolves requested facts and artifacts from authoritative registries, repository maps, plans, source ranges, work relationships, and current state. It enforces access, trust, freshness, and size policy.

## PLAN-CTX-001:SEC-03 Context Compiler

The compiler produces immutable context packs containing task objective, authority, constraints, source references, expected artifacts, acceptance criteria, relevant code map, allowed tools, and return contract. A context receipt records what was actually supplied.

## PLAN-CTX-001:SEC-04 Trust and firewall

Retrieved instructions are classified by origin and authority. Untrusted repository or external text cannot override governing instructions, request secrets, expand tool authority, or silently mutate scope. Suspicious content is isolated and reported.

## PLAN-CTX-001:SEC-05 Freshness and coverage

Each pack records source versions and generation time. Staleness checks invalidate packs after relevant source or state changes. Coverage checks ensure every required acceptance criterion and constraint is represented before delegation.
