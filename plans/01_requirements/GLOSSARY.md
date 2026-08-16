# Project Pipeline Glossary

Terms: `62`

## Acceptance Criterion

A stable, objectively verifiable condition attached to governed work.

Aliases: `AC`
Sources: `SRC-008:L000447-L000519`

## Action Intent

A typed proposed mutation containing actor, authority, scope, target, risk, approval, idempotency, and audit identity.

Sources: `SRC-017:L000072-L000141`

## Adapter

A stable internal interface that isolates an external provider, tool, host, or storage backend.

Aliases: `provider adapter`
Sources: `SRC-005:L000057-L000129`

## Admission Control

The deterministic decision that sufficient budget, capacity, policy, and isolation exist before work starts.

Aliases: `resource admission`
Sources: `SRC-009:L000022-L000022`

## Artifact

A content-addressed file or byte object produced, consumed, tested, or released by the platform.

Sources: `SRC-009:L000016-L000016`

## Assurance Layer

Controls that prevent loops, scope drift, unsupported truth, skipped verification, and false completion.

Aliases: `Execution Assurance`
Sources: `SRC-008:L000005-L000037`

## Autonomy Director

The advisory intelligence that interprets goals and recommends plans while deterministic authority commits state.

Aliases: `Director`
Sources: `SRC-003:L000005-L000084`

## Backpressure

Reduced or stopped admission caused by queue, budget, provider, machine, or verification pressure.

Sources: `SRC-017:L000360-L000438`

## Branch Guardian

Repository governance role that protects branch, base, worktree, and work-in-progress integrity.

Sources: `SRC-007:L000713-L000798`

## Budget Governor

Authority that accounts for spend and quotas and admits billable work through policy.

Sources: `SRC-004:L000005-L000049`

## Budget Pressure

A mode indicating constrained, critical, or exhausted spending and quota capacity.

Sources: `SRC-004:L000373-L000483`

## Build Sequencer

Component that turns accepted work and dependencies into an ordered, recomputable build plan.

Sources: `SRC-003:L000225-L000371`

## Candidate Complete

A worker claim that implementation is ready for independent completion evaluation, not final done state.

Aliases: `IMPLEMENTATION_CANDIDATE_COMPLETE`
Sources: `SRC-008:L000407-L000446`

## Canonical State

The authoritative deterministic project representation used for decisions and transitions.

Sources: `SRC-003:L000044-L000084`

## Capability

A qualified behavior that a worker, model, provider, or tool can supply under known constraints.

Sources: `SRC-001:L001302-L001346`

## Capability Registry

The machine-readable catalog of available capabilities, versions, constraints, cost, resources, and qualification state.

Sources: `SRC-001:L001302-L001346`

## Circuit Breaker

A bounded failure-state mechanism that suppresses repeated unsafe calls and permits controlled recovery probes.

Sources: `SRC-005:L000224-L000282`

## Completion Gate

Deterministic authority that verifies criteria, tests, evidence, review, traceability, blockers, and freshness before done.

Sources: `SRC-008:L000520-L000589`

## Conflict Graph

Graph of work items that cannot run together because of shared or incompatible resources.

Sources: `SRC-014:L000378-L000748`

## Context Broker

Authority that decides which trusted information a worker may and must receive.

Sources: `SRC-002:L000037-L000085`

## Context Compiler

Service that assembles normalized purpose-specific context from authoritative project records.

Sources: `SRC-002:L000146-L000212`

## Context Firewall

Policy boundary that prevents unauthorized data, secrets, or instructions from reaching a provider or worker.

Aliases: `Data-Egress Governor`
Sources: `SRC-009:L000009-L000009`

## Context Pack

An immutable, content-addressed, purpose-specific bundle supplied to a delegated worker.

Sources: `SRC-002:L000213-L000260`

## Context Receipt

Worker acknowledgement of the context consumed, omissions, conflicts, and additional needs.

Sources: `SRC-002:L000359-L000386`

## Control Kernel

Deterministic authority that owns canonical state and admissible transitions.

Aliases: `Project Control Kernel`
Sources: `SRC-003:L000044-L000084`

## Correlation Id

Identifier shared by events, logs, traces, work, evidence, and actions from one logical operation.

Sources: `GOV-001:L000695-L000710`

## Decision Center

Operator surface for inspecting material decisions, inputs, authority, alternatives, and provenance.

Sources: `SRC-006:L001966-L002021`

## Delegation Envelope

Structured assignment containing objective, scope, constraints, sources, outputs, authority, and return protocol.

Sources: `SRC-002:L000086-L000145`

## Disposition

The explicit accepted, superseded, excluded, rejected, or unresolved treatment of a requirement or candidate.

Sources: `GOV-001:L001202-L001215`

## Dynamic Lane

A temporary execution lane derived from eligible work and resources rather than a permanent agent slot.

Sources: `SRC-014:L000378-L000748`

## Evidence

Observed output or state linked to a claim, method, environment, time, revision, and digest.

Sources: `SRC-008:L000595-L000702`

## Evidence Ledger

Append-only registry of evidence records and supersession history.

Sources: `SRC-008:L000595-L000647`

## Fencing Token

Monotonic or unique lease identity used to reject actions from stale owners.

Sources: `SRC-005:L000406-L000441`

## Golden Journey

Stable critical end-to-end scenario that must pass for release readiness.

Sources: `SRC-008:L000956-L000985`

## Human Required

A state in which safe continuation of dependent work requires an operator decision or action.

Aliases: `HUMAN_REQUIRED`
Sources: `SRC-015:L000031-L000150`

## Idempotency Key

Stable operation identity that prevents a retried mutation from duplicating state.

Sources: `SRC-017:L000281-L000359`

## Instruction Trust

Authority and trust classification applied to instructions before they may influence action.

Sources: `SRC-017:L000009-L000071`

## Jira Steward

Governance role that owns Jira synchronization, hygiene, hierarchy, comments, transitions, and reconciliation.

Sources: `SRC-007:L000539-L000624`

## Lease

Time-bounded ownership of a resource with holder, scope, expiry, renewal, release, and fencing identity.

Sources: `SRC-014:L000378-L000748`

## Loop Guard

Control that detects repeated ineffective execution and stops or escalates it.

Sources: `SRC-008:L000038-L000093`

## Merge Gate

Authority that permits integration only when branch, review, policy, test, and evidence conditions are satisfied.

Sources: `SRC-007:L000939-L000969`

## Open Decision

A stable unresolved choice with options, constraints, resolution method, and decision gate.

Sources: `GOV-001:L000110-L000119`

## Operator Inbox

Prioritized queue of human-required decisions and actions with impact and verification instructions.

Sources: `SRC-015:L000031-L000150`

## Outbox

Durable queue of intended external mutations awaiting idempotent delivery and reconciliation.

Sources: `SRC-005:L000730-L000766`

## Project Profile

Policy bundle that selects services, verification, environments, and constraints for a project class.

Sources: `SRC-001:L001255-L001301`

## Provider State

Explicit runtime health and eligibility state used by routing and recovery.

Sources: `SRC-005:L000198-L000223`

## Release Readiness

Evidence-backed determination that applicable release, deployment, operational, security, and recovery conditions are satisfied.

Sources: `SRC-006:L001342-L001398`

## Repository Steward

Governance role that owns branch, worktree, pull-request, protection, cleanup, and reconciliation policy.

Sources: `SRC-007:L000649-L000669`

## Resource Admission

Decision that requested compute and concurrency resources can be allocated safely.

Sources: `SRC-009:L000022-L000022`

## Risk Based Verification

Selection of independent evidence types and test depth according to impact and uncertainty.

Sources: `SRC-008:L001109-L001167`

## Rpo

Maximum acceptable loss of durable state measured from the latest recoverable point.

Aliases: `Recovery Point Objective`
Sources: `SRC-017:L000439-L000489`

## Rto

Maximum acceptable time to restore a required capability after failure.

Aliases: `Recovery Time Objective`
Sources: `SRC-017:L000439-L000489`

## Safe Parallel Set

Set of eligible work items whose conflicts are absent, isolated, or protected by leases.

Sources: `SRC-014:L000378-L000748`

## Scope Governor

Control that enforces accepted work boundaries, change budgets, and scope-change review.

Sources: `SRC-008:L001196-L001270`

## Spend Lease

Bounded authorization for billable or quota-consuming work.

Sources: `SRC-004:L000252-L000306`

## Split Brain

Failure in which more than one controller believes it has canonical mutation authority.

Sources: `SRC-005:L000406-L000441`

## Stale Evidence

Evidence no longer applicable because source, revision, environment, policy, or dependent state changed.

Sources: `SRC-008:L001042-L001066`

## Truth Registry

Registry of material claims and facts with provenance, verification, freshness, and supersession.

Sources: `SRC-008:L000715-L000770`

## Verified Fact

A claim accepted under applicable verification, authority, and freshness policy.

Sources: `SRC-008:L000648-L000770`

## Verified Outcome Cost

Total cost required to produce an accepted result including retries, context, review, and rework.

Aliases: `cost per verified outcome`
Sources: `SRC-004:L000735-L000811`

## Work Item

Stable Jira-mirrored unit of governed implementation, verification, investigation, or recovery work.

Sources: `GOV-001:L000985-L001021`

## Worktree

Git working directory attached to an isolated branch for conflict-safe parallel work.

Sources: `SRC-001:L000492-L000538`
