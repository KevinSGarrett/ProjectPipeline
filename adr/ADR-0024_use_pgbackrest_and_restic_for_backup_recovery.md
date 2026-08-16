# ADR-0024 — Use pgBackRest for PostgreSQL and restic for portable encrypted backup

- **Status:** ACCEPTED
- **Authority:** engineering decision grounded in canonical requirements and bounded upstream review
- **Source references:** `SRC-016:L001057-L001284`, `SRC-017:L000439-L000489`
- **Resolves:** `OPEN-DEC-0022`

## Context

Recovery readiness requires database-aware backup plus portable encrypted backup for non-database state, while backup existence must not be confused with a verified restore.

## Decision

Use pgBackRest for PostgreSQL-specific backup and restore, and restic for portable encrypted repository, artifact, local/offsite, or S3-compatible backup. Treat backup completion and restore verification as separate states.

## Alternatives considered

- Native database backup plus restic
- Cloud snapshots only
- One generic backup tool for all domains

## Consequences

- Uses PostgreSQL-aware recovery mechanics plus portable encrypted repository protection
- Adds two optional external tools that require separate qualification

## Authority boundary

Project Pipeline retains deterministic project-state, recovery, security, budget, lease/fencing, and completion authority. Optional runtimes, backup tools, and cloud services provide bounded mechanics only. Live external qualification requires pinned provenance and environment-specific evidence.
