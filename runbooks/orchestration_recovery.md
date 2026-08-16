# Durable Orchestration Recovery Runbook

Use this runbook when a worker disappears, a durable backend becomes unavailable, a workflow is stuck, or an external mutation has an uncertain result.

1. Query canonical Project Pipeline workflow state and event history before inspecting provider-specific history.
2. Check `orchestration_outbox`. An `UNKNOWN_OUTCOME` operation must not be retried until the remote effect is proven applied or absent.
3. For an expired worker, compare the current fencing epoch, assigned workflow, step recoverability, attempt count, and latest checkpoint. A stale worker must never resume under an older fencing epoch.
4. If the current step is recoverable and attempts remain, allow the recorded bounded retry. If recovery cannot be proven safe, keep the run in `RECOVERY_REQUIRED`.
5. For signal or timer waits, inspect the persisted wait record and inbox before injecting another signal. Duplicate message identities must not cause another state transition.
6. For external-backend outages with no remote run identity, suspend rather than fabricate a successful start. An explicit fallback plan may be considered only if no durable history exists on the original backend.
7. If a remote run identity exists, do not migrate the active history to Hatchet, DBOS, Temporal, or another engine without an explicit migration procedure and compatibility evidence.
8. Preserve recovery decisions, checkpoints, backend observations, and operator actions as evidence. Do not delete uncertain state to make the workflow look healthy.
9. After recovery, verify the canonical run version, current step/attempt, last checkpoint, outbox state, worker fencing epoch, and downstream side effects before normal autonomous execution resumes.
