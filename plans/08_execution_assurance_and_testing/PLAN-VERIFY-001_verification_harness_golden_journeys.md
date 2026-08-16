# PLAN-VERIFY-001 — Verification Harness, Golden Journeys, and Browser Evidence

- **Plan ID:** `PLAN-VERIFY-001`
- **Status:** `ACTIVE`
- **Authority:** deterministic Project Pipeline verification contracts, Execution Assurance Completion Gate, and the permanent Upstream Adoption Gate
- **Source basis:** `SRC-008`, `SRC-014`, `SRC-017`, and `GOV-001` verification/testing requirements

## PLAN-VERIFY-001:SEC-01 Pass-16 upstream activation gate

The completed Pass-15 review is consumed rather than repeated. The exact thirteen verification/evaluation candidates are activation-preflighted before material harness work. Playwright is executed directly in the current environment; optional external tools that are absent remain explicit adapter or qualified-not-installed states. Selection, adapter implementation, installed runtime, and executed evidence remain separate truth states.

## PLAN-VERIFY-001:SEC-02 Profile-driven verification portfolio

A typed verification policy defines required categories, timeout ceilings, evidence freshness expectations, browser behavior, property-case budgets, performance sample counts, and local browser candidates. Required checks may pass, fail, or be explicitly blocked; required checks may never be silently skipped.

## PLAN-VERIFY-001:SEC-03 Contract, API, integration, and end-to-end harness

The harness executes generated-contract tests, provider/Jira/GitHub API adapter contracts, cross-subsystem integration tests, and executable end-to-end journey tests with fixed argv and `shell=False`. A deterministic test-impact derivation maps changed paths and requirement links to the minimum required verification categories and fails safe to broader verification for unknown changes. Stdout/stderr and machine results are persisted as content-addressed verification artifacts.

## PLAN-VERIFY-001:SEC-04 Golden journeys

Canonical golden journeys verify budget hard-stop behavior, durable unknown-outcome reconciliation, Completion Gate refusal of premature completion, and permanent upstream-reuse continuity. Each journey has a stable definition, source requirement links, environment, setup steps, action sequence, expected observable results, cleanup steps, preserved-evidence expectations, risk, and a structured result.

## PLAN-VERIFY-001:SEC-05 Browser and visual evidence

Direct Playwright execution uses the installed Python package and a locally available Chromium executable. The verification report is loaded from a repository-local file, rendered at desktop and mobile viewports, checked for horizontal overflow and console errors, and captured as PNG evidence. Browser evidence remains evidence-producing only.

## PLAN-VERIFY-001:SEC-06 Accessibility and performance evidence

The browser harness performs a deterministic semantic accessibility baseline covering document language, landmarks, heading structure, accessible names, form labels, and duplicate IDs. axe-core remains an optional reviewed-bundle adapter when installed. Performance checks record p50/p95/max measurements against explicit local budgets; Lighthouse CI remains an optional local-target adapter when installed.

## PLAN-VERIFY-001:SEC-07 Adversarial, property, mutation, and fault verification

Adversarial probes challenge silent skip behavior, forged completion, and verifier path containment. Deterministic generated property cases exercise Completion Gate and scheduler invariants. Isolated repository mutation probes must be detected by repository validators. Fault scenarios cover repeatable provider errors, provider latency/timeouts, network loss, lost backend acknowledgement, worker termination, provider quota exhaustion, and optional dependency failure. Optional Hypothesis, mutmut, and Toxiproxy runtimes are not falsely claimed when absent.

## PLAN-VERIFY-001:SEC-08 Verification persistence and evidence ingestion

`PPDB-0013_verification_harness` persists tool activations, verification runs, check results, artifacts, and golden-journey results with reversible SQLite and PostgreSQL-oriented DDL. Verification artifacts are hashed and repository-relative. Fresh passing results may be mapped into the Evidence Ledger and Truth Registry; blocked or failed results cannot be converted into passing facts.

## PLAN-VERIFY-001:SEC-09 Post-merge verification

Post-merge verification reconciles the repository manifest, repository validator, traceability coverage, Evidence Ledger integrity, and the required test-suite state. The post-merge report does not bypass the Completion Gate and cannot make later security, resilience, deployment, or Command Center obligations disappear.

## PLAN-VERIFY-001:SEC-10 Completion recomputation and continuation

Pass 16 supplies executable verification evidence and recomputes the deterministic Completion Gate. Golden-journey evidence may satisfy the corresponding gate question, but unfinished later-pass obligations remain failed. Pass completion requires cumulative regression, repository self-validation, clean archive verification, upstream validation, and generation of the next pass upstream-first gate.

## PLAN-VERIFY-001:SEC-11 Unattended operating-loop qualification

Qualification shall drive a fixture project through intake, verified compilation, genuinely missing implementation, tests, conflict-safe branch and PR handling, merge, Jira reconciliation, next-work recomputation, restart recovery, and truthful Command Center observation. Component invocation or mock-only stages do not qualify the operating loop. After the bounded golden journey and controlled external-write qualification pass, the same governed runtime must pass Windows-native 4-hour, 24-hour, and 72-hour unattended stages. Only a verified 72-hour artifact containing all required end-to-end, recovery, reconciliation, Windows, and unattended facts may satisfy Completion Gate question 16.
