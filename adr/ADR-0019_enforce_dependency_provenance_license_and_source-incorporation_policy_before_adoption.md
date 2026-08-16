# ADR-0019 — Enforce dependency provenance, license, and source-incorporation policy before adoption

- **Status:** `ACCEPTED`
- **Source basis:** `GOV-001:L000797-L000876`, `GOV-001:L001364-L001385`, `SRC-016:L002181-L002195`
- **Date:** `2026-08-14`

## Context

The supplied catalog contains candidates with different licenses, maturity, packaging, security, and maintenance characteristics. Dependency installation and source copying have different legal and operational implications.

## Decision

Require a recorded canonical URL, inspected revision, license classification, subsystem role, review artifact, security and portability notes, and explicit disposition before adoption. Distinguish installing an upstream dependency from copying or adapting source. Permissive licenses may be auto-approved under policy; MPL-family use requires notice and file-level compliance; AGPL or unknown terms require explicit legal approval before incorporation.

## Alternatives considered

- Adopt every repository in the supplied catalog.
- Infer license from project popularity.
- Copy code while retaining only a URL citation.

## Consequences

No upstream source has been copied during this decision. Lockfiles, notices, SBOMs, update review, and revision provenance become release requirements when dependencies are introduced.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
