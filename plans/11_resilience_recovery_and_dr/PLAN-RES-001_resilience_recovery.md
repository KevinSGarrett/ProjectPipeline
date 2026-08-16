# PLAN-RES-001 — Resilience, Recovery, and Disaster Readiness

- **Plan ID:** `PLAN-RES-001`
- **Status:** `PARTIALLY_IMPLEMENTED`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000621-L000641`, `GOV-001:L001666-L001680`, `SRC-012:L000001-L000100`, `SRC-015:L000003-L000112`

## PLAN-RES-001:SEC-01 Failure domains

The Recovery Director models provider, API, network, machine, database, external-system, quota, budget, GPU, and optional cloud failure domains. Deterministic decisions select `FULL`, `DEGRADED`, `LOCAL_FIRST`, `RECOVERY`, `PAUSED`, or `EMERGENCY_STOP` behavior without delegating authority to a model or provider.

## PLAN-RES-001:SEC-02 Durable state and fenced failover

Control-machine takeover fails closed unless the active lease is expired or fenced, the candidate is healthy and explicitly assigned a standby/recovery role, and an independent witness confirms takeover. The next fencing token is monotonic and reconciliation is mandatory before authoritative commits. Durable workflow checkpoints and resource leases remain the source for recoverable execution state.

## PLAN-RES-001:SEC-03 Degraded and local-first operation

Optional provider/cloud/GPU failures preserve deterministic control and unrelated work. Network/cloud loss selects `LOCAL_FIRST`; canonical-state failure selects `RECOVERY`. Capability substitution preserves task semantics and never weakens acceptance, policy, or evidence requirements.

## PLAN-RES-001:SEC-04 Human-required recovery

A scoped human-required incident records the exact action, affected domain, blocked work, unaffected work, repair checks, and stale assumptions. After intervention the system verifies the repair, invalidates stale assumptions, reconciles state, and resumes only eligible work. Machine-readable runbooks define prerequisites, approved actions, stop conditions, verification, and escalation.

## PLAN-RES-001:SEC-05 Recovery objectives and backup

Configured engineering targets are: canonical state RPO 5 minutes/RTO 30 minutes; repository WIP RPO 15 minutes/RTO 30 minutes; evidence and operator history RPO/RTO 60 minutes; artifacts RPO 60 minutes/RTO 120 minutes. pgBackRest is selected for PostgreSQL-specific backup/restore and restic for portable encrypted repository/artifact protection. Backup status is always distinct from isolated restore-verification status.

## PLAN-RES-001:SEC-06 Local intelligence and outage fallback

Ollama, llama.cpp, and optional llama-swap are behind a provider-neutral local gateway. They may support triage, summarization, review, routing assistance, and outage fallback while remaining advisory-only. Model/runtime availability never establishes control authority or completion.

## PLAN-RES-001:SEC-07 Optional cloud recovery spine

The default architecture remains local-primary. An optional AWS support plane may provide a lease witness, durable event queue, recovery storage, watchdog/ingress, observability, budget controls, and bounded recovery. Cloud outage/removal must leave local project truth intact. The repository contains disabled-by-default IaC; it does not claim a live deployment.

## PLAN-RES-001:SEC-08 Verification boundary

Repeatable simulations cover provider loss, control-machine loss, split-brain denial, AWS/network outage, backup/restore planning, and GPU unavailability. External binaries/services and destructive real restores remain separately qualified evidence gates before production-readiness claims.
