# PLAN-UX-001 — Command Center and Operator Experience

- **Plan ID:** `PLAN-UX-001`
- **Status:** `PLANNED`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000643-L000693`, `SRC-015:L000003-L000112`


## PLAN-UX-001:SEC-01 Surfaces

The Command Center is a Windows-capable application with a network-accessible interface. It exposes system and project health, live work, dependencies, completion, context, budgets, providers, risks, approvals, recovery, evidence, Jira/GitHub synchronization, and historical playback.

## PLAN-UX-001:SEC-02 Director interaction

Director Chat is grounded in current project state and scoped to global, project, or incident context. It may explain, propose, and request typed actions. Actions pass through normal authorization, policy, idempotency, and audit controls.

## PLAN-UX-001:SEC-03 Autonomous incident inbox

The inbox consolidates autonomous external-precondition rechecks, policy approvals, incidents, expiring leases, failed verification, security events, and unresolved decisions. Every item includes severity, impact, owning automated capability, affected work, next autonomous probe, and post-recovery verification. It never assigns routine project work to a person.

## PLAN-UX-001:SEC-04 Notifications

A broker applies severity, deduplication, escalation, quiet hours, machine-actionable payloads, and delivery adapters such as Windows tray or remote channels. Status summaries explain what occurred while the system continued unattended.

## PLAN-UX-001:SEC-05 Accessibility and visual quality

The interface requires keyboard navigation, semantic structure, contrast, responsive layouts, clear status language, automated browser checks, accessibility tests, and independent visual review.
