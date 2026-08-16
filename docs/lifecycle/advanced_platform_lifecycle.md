# Advanced Platform Lifecycle

Pass 22 makes lifecycle behavior explicit without creating a second authority plane.

## Multi-project portfolio governance

Each project retains its own control authority, credentials, budget, evidence, context, and permissions. The Portfolio Governor may allocate shared capacity by priority, deadline pressure, guaranteed capacity, maximum share, operator importance, and starvation age, but it cannot rewrite a project's accepted state.

## Multi-repository projects

A project can register multiple repository bindings with explicit roles, revisions, dependency relationships, and stewards. Cross-repository work uses one shared change identity and a declared merge order; every repository remains individually reconciled.

## Environment and test-data lifecycle

Environment types are `LOCAL`, `INTEGRATION`, `PR_PREVIEW`, `STAGING`, `PRODUCTION`, and `TEMPORARY_TEST`. Preview and temporary test environments require TTLs. Destructive test work uses isolated namespaces. Production/production-derived data is denied by default and requires explicit permission plus verified transformation; sensitive test data requires masking evidence.

## Contract evolution

Breaking evolution follows `EXPAND -> MIGRATE -> VERIFY -> CONTRACT`. Contraction/removal is blocked while incompatible consumers remain or verification evidence is absent. Migration and rollback plans are mandatory metadata.

## Retention, closure, and archive

Retention expiry does not authorize deletion. Reference-aware garbage collection requires both expired retention and zero live references, and legal hold blocks the plan. Project closure proceeds through `ACTIVE -> MAINTENANCE -> CLOSING -> ARCHIVED -> DECOMMISSIONED`. Archive readiness requires final requirement verification, signed release, Jira/Git reconciliation, evidence/handoff artifacts, resource/credential/task shutdown plans, and a verified final backup/restore.

## Tool/model/platform qualification

New versions enter `QUALIFICATION` and are excluded from high-risk routing until conformance plus shadow/canary evidence exists. A platform release cannot control real projects without a separately identified release artifact, synthetic end-to-end certification evidence, migration and rollback plans, canary/shadow evidence, and a post-upgrade verification plan.

## Adoption maturity

Existing-project adoption maturity is measured across discovery, baseline, gap analysis, adoption plan, controlled bootstrap, shadow autonomy, limited autonomy, and full-autonomy eligibility. Assessment is read-only and must never mutate authoritative project assets.

## Upstream boundaries

Devcontainers, OpenSpec, Spec Kit, mise, and DVC contribute independently reimplemented patterns. Worktrunk and restic retain their existing bounded adapters. Renovate remains prohibited from activation under the current AGPL license policy.
