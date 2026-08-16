# PLAN-LIFE-001 — Platform Lifecycle and Portfolio Governance

- **Plan ID:** `PLAN-LIFE-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000733-L000747`, `GOV-001:L001736-L001748`


## PLAN-LIFE-001:SEC-01 Multi-project operation

The platform supports isolated projects with shared provider, model, machine, and policy registries. Portfolio coordination cannot erase per-project authority, budget, evidence, or completion state.

## PLAN-LIFE-001:SEC-02 Multi-repository projects

A project may span multiple repositories with explicit roles, dependency relationships, release coordination, and repository-specific stewardship. Cross-repository changes require a shared change identity and reconciliation.

## PLAN-LIFE-001:SEC-03 Contract and data evolution

Schemas, events, APIs, contexts, and adapter contracts are versioned. Compatibility policy, migrations, qualification, and rollback are required before promotion.

## PLAN-LIFE-001:SEC-04 Safe platform change

Self-modification is governed as normal high-risk project work. The platform cannot exempt its own changes from review, evidence, or recovery requirements.

## PLAN-LIFE-001:SEC-05 Closure and retention

Project closure verifies final state, archives sources and evidence, resolves external synchronization, records retention and deletion policy, and preserves sufficient context for audit or later reactivation.


## PLAN-LIFE-001:SEC-06 Pass 22 executable lifecycle boundary

Pass 22 implements deterministic lifecycle models and planners under `src/project_pipeline/lifecycle/`, reversible persistence migration `PPDB-0018`, a Project Pipeline-owned lifecycle policy, five lifecycle fault simulations, and repository validation. External destructive cleanup, live project closure side effects, cloud teardown, credential revocation, and platform promotion remain typed/evidence-gated operations and are not inferred from an eligibility decision.
