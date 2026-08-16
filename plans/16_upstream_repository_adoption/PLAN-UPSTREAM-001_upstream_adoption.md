# PLAN-UPSTREAM-001 — Upstream Repository Evaluation and Adoption

- **Plan ID:** `PLAN-UPSTREAM-001`
- **Status:** `ACTIVE`
- **Authority:** source-derived requirements plus accepted dependency decisions
- **Source basis:** `GOV-001:L000797-L000876`, `SRC-010:L001521-L001711`, `SRC-016:L001691-L001832`, `SRC-016:L002181-L002195`

## PLAN-UPSTREAM-001:SEC-01 Registry scope

Every supplied repository has a stable upstream ID, canonical URL, expected local path, subsystem classification, inspection state, license state, revision state, disposition, disposition rationale, source-incorporation state, and provenance requirements. Reviewed candidates add purpose, useful modules, integration boundary, security, portability, maturity, compatibility, maintenance, and dependency impact.

## PLAN-UPSTREAM-001:SEC-02 Review sequencing

Review is prioritized by unresolved architecture decision, subsystem value, security impact, integration criticality, and maintenance risk. A bounded cohort is inspected at one time. Unreviewed repositories remain cataloged and non-activatable; no model context should load the full catalog simultaneously.

## PLAN-UPSTREAM-001:SEC-03 Dispositions

Allowed dispositions are `ADOPT_DEPENDENCY`, `ADAPT_COMPONENT`, `MINE_ARCHITECTURE`, `MINE_IMPLEMENTATION_PATTERN`, `MINE_TEST_PATTERN`, `EVALUATE_LATER`, `REJECT`, and `NOT_RELEVANT`. Every entry has exactly one disposition and rationale. `ADOPT_DEPENDENCY` grants bounded activation eligibility, not permission to copy source.

## PLAN-UPSTREAM-001:SEC-04 Evaluation record

A focused review records the canonical origin, inspected revision, observed local revision or its absence, license, useful files, architecture lessons, integration options, security concerns, portability, maintenance, maturity, compatibility, dependency implications, and evidence sources. Review artifacts are revision-pinned and queryable by stable ID.

## PLAN-UPSTREAM-001:SEC-05 Architecture rule

Mature commodity capability may be reused through a stable adapter. Project Pipeline retains internal ownership of control, truth, policy enforcement, resource admission, completion, evidence, and reconciliation semantics. Official maintained integrations receive evaluation priority when they satisfy the same requirements.

## PLAN-UPSTREAM-001:SEC-06 Current adoption boundary

Selected dependencies are approved only for the roles and constraints in `architecture/technology_stack.json`. Version locking, vulnerability review, SBOM generation, notice preservation, and conformance testing are activation gates. Qualified alternatives remain non-default.

## PLAN-UPSTREAM-001:SEC-07 Evolution and re-review

Later research may narrow or supersede an earlier recommendation only through an explicit source-evolution record and ADR. License, ownership, archival, security, major-version, or maintenance changes trigger re-review. Previous observations remain discoverable.
