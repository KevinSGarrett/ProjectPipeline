# PLAN-REQ-001 — Requirements Engineering and Traceability

- **Plan ID:** `PLAN-REQ-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000123-L000221`, `GOV-001:L001162-L001215`, `SRC-008:L000648-L000760`


## PLAN-REQ-001:SEC-01 Requirement identity

Every requirement receives a stable domain-prefixed ID and records its statement, type, authority, source references, chronology, disposition, risk, plan IDs, work-item IDs, implementation paths, test IDs, evidence IDs, and current implementation state.

## PLAN-REQ-001:SEC-02 Provenance and chronology

Canonical source lines are retained using exact `SRC-NNN:Lxxxxxx-Lxxxxxx` references. Governing requirements use `GOV-001:Lxxxxxx-Lxxxxxx`. Exact duplicates are not counted as independent confirmation. Later sources may refine or supersede earlier recommendations, but the earlier record remains discoverable.

## PLAN-REQ-001:SEC-03 Requirement classes

The registry supports functional, nonfunctional, constraint, interface, security, resilience, operational, testing, completion, and governance requirements. Engineering-added detail must declare its authority classification rather than being silently presented as source-derived.

## PLAN-REQ-001:SEC-04 Disposition model

Accepted requirements progress through `PLANNED_ONLY`, `PARTIALLY_IMPLEMENTED`, `IMPLEMENTED`, `MOCK_VERIFIED`, `LIVE_VERIFIED`, or `BLOCKED_EXTERNAL`. A separate disposition records accepted, superseded, excluded, rejected, or open-decision state.

## PLAN-REQ-001:SEC-05 Bidirectional mappings

Machine-readable registries map source to requirement; requirement to plan, decision, work, implementation, tests, and evidence; and implementation, test, or work back to requirement and source. Validators reject dangling identifiers and unexplained gaps.

## PLAN-REQ-001:SEC-06 Coverage computation

Coverage is computed from registry facts rather than document counts. A requirement is fully mapped only when all required relationships are present. Verification coverage additionally requires applicable tests and current evidence. Unknown remains an explicit state.
