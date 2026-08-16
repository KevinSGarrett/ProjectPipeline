# Developer Guide

Project Pipeline is a `src/`-layout Python package with deterministic authority separated from optional adapters. Start with `README.md`, `docs/NAVIGATION.md`, the plans, Jira mirror, architecture catalogs, and the source/requirement traceability exports.

For changes: identify linked requirements and Jira work; inspect the owning subsystem; preserve authority and side-effect boundaries; implement; add behavior-specific tests; run impact-selected verification; update evidence and traceability; run repository validation; and regenerate canonical assets. Never treat an upstream framework, scanner, model, CI action, UI, or deployment wrapper as canonical project state or release authority.

Release-affecting changes additionally require the Pass 24 hardening validator, dependency-state review, SBOM/provenance refresh, performance/security/resilience checks, archive verification, rollback material, and the independent Completion Gate.
