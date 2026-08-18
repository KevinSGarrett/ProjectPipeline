# Blocked-External Recovery Runbook

Use `BLOCKED_EXTERNAL` only after safe autonomous discovery and recovery paths are exhausted and an external precondition remains objectively unavailable. The incident record must identify the affected failure domain, exact blocked capability, blocked work, unaffected work that continues, autonomous verification probes, and assumptions invalidated after the next recheck. New state or evidence must never emit the retired human-work status.

Do not assign operator work. Schedule an autonomous recheck of the dependency instead of treating any chat report as completion. Reconciliation runs against canonical state, stale observations are invalidated, and only currently eligible work resumes. A scoped incident does not stop unrelated lanes unless the failed resource is truly global.
