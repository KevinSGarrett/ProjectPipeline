# Transactional Traceability Projection

Project Pipeline persists the complete requirement graph as normalized links without weakening the validated repository catalog.

## Import

`RequirementTraceabilityService.import_authoritative_catalog()` parses all requirement rows as strict entities, imports them transactionally, records catalog identity and digest, and rebuilds normalized links. Re-import is idempotent when the catalog is unchanged.

## Queries

The service supports:

- requirement-to-source, plan, Jira, implementation, test, evidence, decision, open-decision, and evolution traversal;
- source-to-requirement lookup;
- arbitrary target-to-requirement lookup by link type;
- persisted-versus-authoritative equivalence checks.

## Mutations

A mutation declares requirement ID, operation, link type, target, expected revision, actor, correlation ID, and reason. A changed mutation increments the requirement revision exactly once. A semantic no-op preserves the revision. Stale expected revisions fail closed. Every accepted mutation receives an immutable audit record.

Mutations are marked `PROPOSED_CHANGE`. Exported projections are review artifacts and do not replace a project's authoritative requirement registry automatically.
