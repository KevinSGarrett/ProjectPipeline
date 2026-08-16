# PLAN-GOV-001 — Jira and Repository Governance

- **Plan ID:** `PLAN-GOV-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `SRC-007:L000380-L000449`, `SRC-007:L000500-L000623`, `SRC-007:L001076-L001090`, `GOV-001:L000949-L001158`


## PLAN-GOV-001:SEC-01 Jira authority and mirror

Jira is the authoritative collaborative work system when connected. The local `/jira` representation is a portable, AI-retrievable, schema-validated mirror that preserves richer semantic relationships when remote Jira cannot represent them directly.

## PLAN-GOV-001:SEC-02 Work-item completeness

Every work item includes stable identity, parent, objective, rationale, scope, exclusions, requirements, sources, plans, dependencies, artifacts, acceptance criteria, verification, Definition of Done, evidence, risk, security, observability, recovery, required capability, state, and completion evidence.

## PLAN-GOV-001:SEC-03 Lifecycle and reconciliation

Remote and local updates are compared by stable mapping and observed version. Conflicts are reconciled explicitly; neither side is overwritten silently. Invalid parentage, dangling relationships, orphan epics, and contradictory dependencies fail validation.

## PLAN-GOV-001:SEC-04 Repository stewardship

The Repository Steward manages branch/worktree isolation, ownership, review state, merge gating, cleanup, backup, and post-merge reconciliation. Short-lived branches include work-item identity. Uncommitted work is preserved rather than discarded by automation.

## PLAN-GOV-001:SEC-05 Completion transition

A work item reaches completion only after applicable acceptance criteria, tests, independent review, documentation, traceability, evidence, security checks, and blockers are satisfied. Jira status must reflect actual implementation state rather than aspirational progress.
