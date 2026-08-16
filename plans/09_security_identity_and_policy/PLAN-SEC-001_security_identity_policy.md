# PLAN-SEC-001 — Security, Identity, Policy, and Supply Chain

- **Plan ID:** `PLAN-SEC-001`
- **Status:** `PLANNED`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000586-L000605`, `GOV-001:L001364-L001385`, `GOV-001:L002184-L002196`


## PLAN-SEC-001:SEC-01 Identity and authority

Human and autonomous identities receive explicit roles, scopes, project membership, environment boundaries, and approval authority. Least privilege applies to files, providers, tools, networks, data, budgets, and mutation operations.

## PLAN-SEC-001:SEC-02 Action intent

A mutating action requires typed intent, actor, target, operation, scope, authorization evidence, policy result, idempotency key, expected effect, and audit correlation. External mutation is denied by default.

## PLAN-SEC-001:SEC-03 Instruction trust

Instructions are evaluated by origin, signature or trusted location where applicable, project authority, and conflict with governing policy. Prompt injection and data-origin confusion are treated as security threats, not only model-quality issues.

## PLAN-SEC-001:SEC-04 Secrets and egress

Secrets are referenced rather than stored in project files. Runtime retrieval, rotation, revocation, audit, and redaction are required. Egress is constrained by destination, data class, provider, tool, and project policy.

## PLAN-SEC-001:SEC-05 Supply chain

Imported and generated code is untrusted until verified. Controls include secret scanning, dependency and vulnerability review, license and provenance records, lock integrity, static analysis, policy evaluation, software bills of materials, artifact integrity, and hardened CI permissions.
