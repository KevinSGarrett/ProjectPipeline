# Blocked-External Recovery Runbook

`HUMAN_REQUIRED` is a compatibility alias for `BLOCKED_EXTERNAL`. Use this state only after autonomous recovery is exhausted or an external precondition remains unmet. The incident record must identify the affected failure domain, exact blocked capability, blocked work, unaffected work that may continue, verification steps, and assumptions that must be invalidated after the next autonomous recheck.

Do not assign operator work. Schedule an autonomous recheck of the dependency instead of treating any chat report as completion. Reconciliation runs against canonical state, stale observations are invalidated, and only currently eligible work resumes. A scoped incident does not stop unrelated lanes unless the failed resource is truly global.
