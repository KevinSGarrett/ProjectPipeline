# Jira Steward

Project Pipeline’s Jira subsystem keeps two truths distinct:

- `/jira` is the source-controlled, AI-retrievable work definition and relationship mirror.
- connected Jira is the external collaboration and work-management surface.

The Jira Steward validates the local mirror, captures immutable remote snapshots, computes deterministic differences, persists an outbox, and performs only explicitly approved remote mutations. It never treats a failed response as proof that a write did not happen.

Start here:

- [`local_mirror.md`](local_mirror.md) — issue model, hierarchy, relationships, and serialization
- [`remote_adapter.md`](remote_adapter.md) — provider port, Jira Cloud adapter, credentials, and errors
- [`reconciliation.md`](reconciliation.md) — snapshots, diff, conflicts, outbox, and unknown outcomes
- [`operator_workflows.md`](operator_workflows.md) — CLI workflows and approval boundaries
- [`../../plans/07_jira_and_repository_governance/PLAN-GOV-002_jira_steward_and_synchronization.md`](../../plans/07_jira_and_repository_governance/PLAN-GOV-002_jira_steward_and_synchronization.md) — technical authority
