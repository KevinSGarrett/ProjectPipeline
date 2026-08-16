# PLAN-SCHED-001 — Sequencing and Conflict-Safe Parallel Execution

- **Plan ID:** `PLAN-SCHED-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000424-L000455`, `GOV-001:L001533-L001558`, `SRC-003:L000040-L000083`


## PLAN-SCHED-001:SEC-01 Work graph

Accepted work is represented as a directed dependency graph with explicit blockers, readiness predicates, priority, risk, expected artifacts, required capabilities, and resource claims. Graph validation rejects cycles unless a documented iterative relationship is intentionally modeled outside the blocking graph.

## PLAN-SCHED-001:SEC-02 Build sequencing

The sequencer computes eligible work from accepted requirements, dependencies, policy, environment availability, unresolved decisions, and evidence state. It recomputes after source, scope, dependency, implementation, or verification changes.

## PLAN-SCHED-001:SEC-03 Conflict graph

Parallel eligibility is constrained by conflicts over files, schemas, branches, worktrees, environments, ports, machines, GPUs, credentials, databases, provider quotas, and other shared resources. A safe set contains no unmitigated conflict edge.

## PLAN-SCHED-001:SEC-04 Leases and ownership

Resource access uses bounded leases with holder identity, scope, acquisition time, expiry, renewal, fencing token, and release evidence. Expired ownership is reconciled before reassignment to prevent split-brain writes.

## PLAN-SCHED-001:SEC-05 Admission and backpressure

Admission considers worker capability, machine capacity, budget pressure, provider health, queue age, risk, and expected verification cost. Backpressure reduces or suspends lower-value work before critical control, recovery, or verification tasks.

## PLAN-SCHED-001:SEC-06 Verification strategy

Property tests exercise graph invariants and safe-set selection. Simulations cover resource contention, lease expiry, machine loss, quota exhaustion, and changing dependencies. Integration tests verify scheduler decisions against persistent state.
