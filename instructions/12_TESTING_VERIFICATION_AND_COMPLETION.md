# Testing, Verification, and Completion

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-12` |
| Status | `ACTIVE` |
| Pack version | `1.0.0` |
| Primary domains | `testing`, `evidence`, `completion` |
| Governing entry point | `AGENTS.md` |

## Risk-proportional sequence

Use this normal development ladder:

```text
targeted falsifying test
→ implementation
→ targeted tests
→ related subsystem tests
→ risk-based PR validation
→ integrated-main verification
```

Do not rerun a long full suite after every one-line edit. Do not stop at a single unit test when acceptance spans integration, recovery, security, UI, migration, or live external behavior.

## Verification plan

Map each acceptance criterion to a method, environment, tool capability, expected evidence, freshness requirement, and failure response. Verification Harness selects profiles and records content-addressed evidence. If a required capability is unavailable, mark the criterion blocked; do not silently skip it.

## Evidence quality

Evidence proves a specific claim. It includes identity, criterion and requirement links, method, environment, observed result, time, digest, and freshness. Examples include test output, browser evidence, API contract result, migration round trip, restored backup, post-merge result, and live integration observation.

A Jira transition, PR status, code listing, or model statement is not evidence alone.

## Test failure policy

Do not remove, weaken, skip, or rewrite a test solely to obtain green output. Trace the test to requirement and acceptance, determine whether implementation, test, fixture, or source is wrong, change the correct artifact, and preserve rationale. Intentional PPQS failures and malformed inputs remain benchmark data.

## Definition of Done

Applicable completion requires:

- accepted implementation and acceptance criteria;
- required deterministic and behavioral tests;
- security/supply-chain checks;
- evidence with valid freshness;
- source-to-evidence traceability;
- required self and independent review;
- merge to the integrated branch;
- post-merge verification;
- Jira reconciliation;
- generated artifacts updated through canonical tools;
- no unresolved blocking defect.

The deterministic Completion Gate remains authoritative. Project Control completion projection is input, not final authority.

## High-risk areas

Authority logic, Completion Gate, external writes, secrets, authentication, persistence/migrations, orchestration recovery, concurrency/fencing, budget enforcement, release, backup/restore, benchmark boundaries, instructions, and policy require stronger independent methods and rollback proof.

## Completion honesty

Never claim live verification from mocks, production readiness while activation is blocked, successful integration while remote systems were unavailable, Windows verification from Linux-only execution, or completion without required evidence. `UNKNOWN` remains unknown; `BLOCKED_EXTERNAL` remains blocked.

## Post-merge verification

Evaluate the actual integrated `main` SHA with risk-appropriate breadth. Confirm required checks, no integration conflict, affected golden journeys, evidence identity, Jira state, and cleanup eligibility. Documentation-only changes do not require every benchmark; consequential control changes do.

## Project completion

Project-wide completion additionally requires accepted disposition of all requirements, no unexplained work gaps, all final gate dimensions, release/install/recovery evidence, operator-visible accurate state, and continuation material independent of chat. Only the Completion Gate may declare it.
