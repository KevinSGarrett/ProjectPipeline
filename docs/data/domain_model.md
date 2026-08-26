# Domain Model

Project Pipeline now has strict, immutable Pydantic entities for project manifests, requirements, project state, task state, state transitions, traceability links, traceability mutations, and database migrations.

## Stable identity

Identifiers are validated by semantic kind. Human-readable project, work-item, verification, decision, and migration identifiers retain their established forms. Transition, trace-link, import, and mutation identifiers are content-derived SHA-256 digests with kind-specific prefixes. Repeating the same semantic operation yields the same identifier.

## Project manifest

Project manifests are local workspace records. They identify a project's source, work model, and verification records without turning a repository's private planning or operational history into published source. Their semantic fingerprint excludes timestamps, so an unchanged rebuild is byte-stable and does not increment the revision.

## State authority

Project and task state use explicit lifecycle enums, allowed-transition tables, optimistic versions, immutable transition records, actor identity, correlation identity, and reasons. Invalid or stale transitions fail before state is changed. A blocked state requires a bounded reason, and non-blocked state rejects a stale blocked reason.

## Requirement entity

Each requirement record parses as a strict `RequirementRecord`. Exact source references, work IDs, decisions, implementation paths, tests, and verification links are validated by semantic type. Implemented records retain their implementation, test, and verification links.
