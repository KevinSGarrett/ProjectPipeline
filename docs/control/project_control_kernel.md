# Project Control Kernel and Build Sequencer

Project Pipeline evaluates accepted project state through deterministic control services. The Project Control Kernel owns readiness and transition admissibility; probabilistic systems may recommend work but do not commit canonical state.

## Inputs

The current implementation consumes the source-controlled Jira mirror, accepted requirement catalog, and persistent project/task state. Every dependency endpoint must resolve. Blocking cycles fail closed. Structural epics are not executable work.

## Eligibility and readiness

Eligibility excludes terminal, already-active, blocked/failed, human-required, externally blocked, unaccepted, and policy-ineligible work. Readiness then evaluates dependency completion, explicit blockers, approval, context, resources, and environment. One blocked item does not prevent unrelated ready work from continuing.

## Sequencing

The Build Sequencer uses NetworkX for bounded DAG primitives. Project Pipeline retains the semantics. Ranking considers explicit priority, zero-slack criticality, deadline pressure when present, risk, downstream unblock value, and declared duration. Stable task identifiers break ties. Missing duration estimates are represented as a 60-minute heuristic rather than invented precision.

## Scope and completion

Scope reconciliation compares accepted requirements and Jira work with implementation/evidence mappings and explicit dependencies. Completion recomputation is intentionally not the final Completion Gate: this subsystem may report `READY_FOR_COMPLETION_GATE`, but it cannot self-approve final completion.

## Mutation boundary

`control ready-plan` is read-only. `control ready-apply` requires both `--apply` and `--approve`, then uses optimistic task-state versions. Other project transitions remain governed by the existing state service until later control-plane convergence work is completed.
