# ADR-0013 — Use content-addressed artifacts with PostgreSQL metadata and filesystem or S3-compatible bytes

- **Status:** `ACCEPTED`
- **Source basis:** `SRC-009:L000015-L000017`, `SRC-015:L000237-L000301`
- **Date:** `2026-08-14`

## Context

Evidence, logs, screenshots, context packs, archives, and other large immutable outputs require verifiable identity, retention metadata, and replaceable local or cloud storage.

## Decision

Address artifact bytes by SHA-256. Store ownership, classification, media type, size, retention, lineage, verification, and storage-location metadata in PostgreSQL. Use a managed local filesystem backend first and an S3-compatible backend for cloud or shared profiles. Database rows reference immutable content identities rather than mutable filenames.

## Alternatives considered

- Store arbitrary large bytes directly in every operational table.
- Use mutable path names as evidence identity.
- Make an object-store service mandatory for local development.

## Consequences

Garbage collection must be reference-aware and policy-controlled. Byte backends require integrity checks and reconciliation. Artifact presence alone never proves an acceptance criterion.

## Review trigger

Revisit this decision when conformance evidence, operational incidents, licensing changes, platform constraints, or measured workload characteristics invalidate its assumptions.
