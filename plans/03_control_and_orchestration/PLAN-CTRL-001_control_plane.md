# PLAN-CTRL-001 — Control Plane and Orchestration Authority

- **Plan ID:** `PLAN-CTRL-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `SRC-003:L000040-L000083`, `SRC-003:L000880-L000960`, `SRC-014:L000001-L000115`, `GOV-001:L000412-L000422`


## PLAN-CTRL-001:SEC-01 Control responsibilities

The control plane owns canonical project state, requirement acceptance, work eligibility, dependency truth, scope boundaries, authorization, policy evaluation, completion recomputation, and reconciliation after change.

## PLAN-CTRL-001:SEC-02 Authority separation

- Project Control Kernel: deterministic state and transition authority.
- Autonomy Director: portfolio and project coordination.
- Architecture Authority: bounded architectural proposals and decision preparation.
- Review Authority: independent findings and verification disposition.
- Completion Authority: evidence-backed final gate.
- Jira and Repository Stewards: synchronized external-system state within policy.

No role may self-approve high-risk work when separation is required.

## PLAN-CTRL-001:SEC-03 State transitions

Transitions require a valid source state, authorized actor or policy, satisfied preconditions, idempotency identity, and an audit event. Unknown outcomes enter reconciliation instead of being retried blindly.

## PLAN-CTRL-001:SEC-04 Durable execution

Long-running actions require persistent workflow identity, checkpoints, retry classification, idempotency keys, transactional boundaries, outbox/inbox handling where needed, and recovery after worker or control-process loss.

## PLAN-CTRL-001:SEC-05 Recommendation boundary

Models may recommend sequencing, context, risk, or remediation. Deterministic validators decide whether the recommendation is admissible. Plan conflicts are recorded and rejected or escalated; they are never silently resolved by model preference.
