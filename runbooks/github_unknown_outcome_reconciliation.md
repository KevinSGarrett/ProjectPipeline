# GitHub Unknown-Outcome Reconciliation

Use this runbook when a GitHub mutation may have reached the provider but Project Pipeline did not receive a definitive response.

1. Stop automatic replay of the affected operation.
2. Read the persisted operation identity, semantic fingerprint, target, expected head SHA, actor, and correlation ID.
3. Perform read-only GitHub observations for the intended effect: branch existence/SHA, pull-request state, merge commit, or branch deletion.
4. Compare the observed state to the planned effect and expected revision.
5. If the effect is independently confirmed, mark the operation reconciled and record the observed external identity/evidence.
6. If the effect is absent and a retry is still authorized, create a new bounded execution attempt using the same semantic intent and an explicit reconciliation decision.
7. If state is divergent or evidence is ambiguous, require human resolution; do not guess and do not issue a duplicate mutation.

Never use local mock state as proof that a live GitHub mutation occurred.
