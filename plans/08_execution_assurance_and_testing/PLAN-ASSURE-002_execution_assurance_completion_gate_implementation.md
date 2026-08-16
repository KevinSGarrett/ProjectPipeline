# PLAN-ASSURE-002 — Execution Assurance and Completion Gate Implementation

- **Plan ID:** `PLAN-ASSURE-002`
- **Status:** `ACTIVE`
- **Authority:** deterministic Project Pipeline assurance contracts, source-derived completion requirements, and the permanent Upstream Adoption Gate
- **Source basis:** `SRC-008:L000038-L001270`, `SRC-008:L000540-L000760`, `GOV-001:L000533-L000584`, `GOV-001:L002028-L002144`

## PLAN-ASSURE-002:SEC-01 Upstream-first verification portfolio gate

Pass 15 evaluates the thirteen verification/evaluation repositories mapped by the permanent Upstream Adoption Gate before material assurance implementation. Promptfoo and Inspect AI reuse existing safe adapters. Hypothesis, Playwright, Playwright MCP, Schemathesis, Toxiproxy, axe-core, Lighthouse CI, mutation tooling, evaluation harnesses, and agent-browser are qualified for the later executable verification portfolio. Upstream tools may generate evidence but cannot self-certify Project Pipeline completion.

## PLAN-ASSURE-002:SEC-02 Acceptance Criteria Compiler and executable Definition of Done

Acceptance criteria compile into stable typed criterion identities with frozen semantic fingerprints, requirement links, risk, objective verification methods, commands, and paths. Criteria without an objective verification mechanism remain explicitly non-objective rather than being treated as complete. Verification plans impose bounded verification attempts and evidence ceilings.

## PLAN-ASSURE-002:SEC-03 Truth Registry, Evidence Ledger, and freshness

Claims, evidence, verified facts, unknowns, and contradictions remain distinct truth states. Verified facts require evidence; unknowns cannot carry passing evidence. Evidence assessments preserve verification status and failure/block states and apply an explicit freshness ceiling. Stale or unverified evidence cannot establish a passing fact merely because it once reported success.

## PLAN-ASSURE-002:SEC-04 Loop Guard, attempt budgets, novelty, and progress

The Loop Guard evaluates stable action, tool, output, state, failure, and progress fingerprints. Attempt exhaustion, repeated failures, and repeated unchanged output stop and escalate work. Repeated action/tool patterns without measurable progress require novelty before another attempt. Genuine recent progress permits continuation while the configured ceilings remain unexhausted.

## PLAN-ASSURE-002:SEC-05 Scope Governor, acceptance freeze, and change budget

Each controlled task may carry a frozen scope contract covering included and excluded behavior, allowed paths, escalation conditions, and a frozen acceptance fingerprint. Work inside that boundary proceeds normally. New behavior or path scope requires review, and exhausted autonomous change budget prevents silent scope expansion or endless plan rewriting.

## PLAN-ASSURE-002:SEC-06 Independent review and risk-based evidence multiplicity

Reviewer identity includes reviewer/implementer separation, independent context fingerprints, and conflicts. Higher-risk criteria require multiple materially distinct fresh evidence methods and a clean independent review. Self-review, shared implementation context, active conflicts, or blocking review findings cannot satisfy the independent-review requirement.

## PLAN-ASSURE-002:SEC-07 Lazy-completion challenge and candidate-complete state

A worker or implementation path may propose candidate completion, but missing criteria, stale evidence, unknown facts, or missing independent review challenge that claim. A candidate may reach `READY_FOR_COMPLETION_GATE` only after criterion/evidence/review prerequisites pass; this state is explicitly not equivalent to final project completion.

## PLAN-ASSURE-002:SEC-08 Deterministic fifteen-question Completion Gate

Final completion requires all fifteen source-derived convergence questions to pass across requirements, implementation traceability, critical-path testing, golden journeys, security, resilience, deployment, rollback, engineer operability, AI continuation, unresolved-state truth, Command Center truth, Jira truth, and zero unexplained coverage gaps. Any failed question produces a localized typed failure and rework route. External-only blockers may yield `BLOCKED_EXTERNAL`, never `COMPLETE`.

## PLAN-ASSURE-002:SEC-09 Persistence, CLI, simulations, and failure routing

`PPDB-0012_execution_assurance_completion_gate` persists immutable verification plans, truth records, independent reviews, loop decisions, scope contracts/changes, and gate evaluations with reversible SQLite and PostgreSQL-oriented DDL. The CLI exposes status, compile, candidate challenge, loop guard, scope change, Completion Gate evaluation, and deterministic simulations. Persisting assurance decisions requires explicit apply and approval flags.

## PLAN-ASSURE-002:SEC-10 Pass-15 verification boundary and continuation

Pass 15 verifies the deterministic assurance authority, not the complete Pass-16 verification harness. Property/stateful, browser/visual/accessibility/performance/fault, mutation, API fuzzing, golden journeys, and post-merge verification remain later executable verification work unless already independently evidenced. The current repository is therefore expected to evaluate `NOT_COMPLETE` until later-pass requirements converge; this is a successful anti-lazy-completion result, not a failure of the gate.
