# PLAN-REL-001 — Release, Handoff, and Completion Audit

- **Plan ID:** `PLAN-REL-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000782-L000792`, `GOV-001:L001884-L001992`, `GOV-001:L002107-L002180`


## PLAN-REL-001:SEC-01 Release candidate

A release candidate is built from the complete canonical workspace, not a patch directory. It contains prior accepted work, current manifests, required documentation, implementation, tests, deployment assets, and evidence.

## PLAN-REL-001:SEC-02 Release checks

Checks include tests, repository policy, plans and identifiers, Jira graph, traceability, references, placeholders, secrets, provenance, archive structure, archive integrity, and exact digests.

## PLAN-REL-001:SEC-03 Handoff state

Handoff identifies implemented, partial, mock-verified, live-verified, externally blocked, and planned work; current decisions; unresolved questions; source and requirement coverage; Jira state; tests; evidence; expected archive; and precise continuation instructions.

## PLAN-REL-001:SEC-04 Completion audit

Full completion requires convergence across sources, requirements, plans, decisions, work, code, configuration, infrastructure, tests, evidence, documentation, deployment, recovery, security, and operations. No single status flag may substitute for this audit.

## PLAN-REL-001:SEC-05 Archive integrity

Archives are opened and tested after creation. The expected root, file inventory, digests, absence of secrets and scratch artifacts, and consistency with the project manifest are verified before delivery.
