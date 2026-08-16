# Human-Required Recovery Runbook

Use this state only after autonomous recovery is exhausted or policy requires a human action. The incident record must identify the affected failure domain, exact requested action, blocked work, unaffected work that may continue, verification steps, and assumptions that must be invalidated after the action.

After the operator reports a repair, Project Pipeline rechecks the dependency instead of trusting the report as completion. Reconciliation runs against canonical state, stale observations are invalidated, and only currently eligible work resumes. A scoped incident does not stop unrelated lanes unless the failed resource is truly global.
