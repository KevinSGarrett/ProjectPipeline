# PLAN-ARCH-004 Core State, Persistence, and Transactional Traceability

**Status:** ACTIVE  
**Authority:** `GOV-001:L000711-L000731`, `GOV-001:L001477-L001488`, `SRC-003:L000852-L001000`, `SRC-009:L000020-L000020`, `SRC-016:L000089-L000093`, `SRC-017:L000264-L000270`, `SRC-017:L000490-L000596`, `SRC-017:L000823-L000906`  
**Related plans:** `PLAN-ARCH-001`, `PLAN-ARCH-002`, `PLAN-REQ-002`, `PLAN-CTRL-001`, `PLAN-GOV-001`, `PLAN-LIFE-001`, `PLAN-LIFE-002`, `PLAN-ASSURE-001`

## PLAN-ARCH-004:SEC-01 Purpose and bounded outcomes

This plan establishes the first executable canonical-state slice for Project Pipeline. It defines stable domain identities, strict requirement entities, a domain project manifest, explicit project and task lifecycle state, production and local persistence boundaries, reversible migrations, transactional requirement traceability, query and mutation services, CLI access, validation, tests, and evidence.

The bounded result must:

- retain the validated JSON/JSONL registries as source authority during migration;
- compile those registries into typed, queryable persistent state;
- keep deterministic authority outside language-model memory;
- make project and task transitions explicit, versioned, and auditable;
- support bidirectional source/plan/Jira/code/test/evidence traversal;
- fail closed on invalid identifiers, transitions, schema input, or stale revisions;
- provide a production PostgreSQL schema behind replaceable repository ports;
- provide an executable SQLite local profile with equivalent semantic entities;
- create no external Project Pipeline mutation.

## PLAN-ARCH-004:SEC-02 Stable domain identities

Project, requirement, Jira, plan, plan-section, acceptance, evidence, decision, and migration identifiers retain their established human-readable forms. Content-derived operational identifiers use SHA-256 over canonical semantic parts and a type-specific prefix:

- `TRACE-` for normalized traceability links;
- `TRANS-` for immutable state transitions;
- `IMPORT-` for catalog imports;
- `MUT-` for traceability mutation audit records.

Identifiers are validated by semantic kind. An unknown or ambiguous identifier is rejected. Repeating the same semantic operation produces the same digest identifier, allowing deterministic reconciliation without conflating different entity types.

## PLAN-ARCH-004:SEC-03 Typed requirements and project manifest

Every row in `plans/_traceability/requirements.jsonl` is represented by strict `RequirementRecord` validation. Exact source ranges, plan and section identities, Jira identities, decisions, implementation paths, tests, evidence, dispositions, and implementation states remain explicit. Completed requirement states require implementation, test, and evidence links.

`config/project_manifest.json` is the domain manifest for the controlled project. It is distinct from the root file-integrity manifest. The domain manifest records:

- project identity and revision;
- project origin and runtime profile;
- exactly one primary repository;
- authoritative source, requirement, plan, Jira, and evidence locations;
- semantic fingerprint and UTC lifecycle timestamps.

An unchanged manifest rebuild is byte-stable and does not increment the revision.

## PLAN-ARCH-004:SEC-04 Project and task state model

Project and task lifecycle state is deterministic. Each state record carries an optimistic version, updated timestamp, and the last immutable transition identity. Task state additionally carries priority, dependencies, blockers, owner, and bounded block reason.

Allowed transitions are explicit tables. A transition requires:

- entity type and identity;
- previous and next state;
- expected and resulting versions;
- actor identity;
- correlation identity;
- bounded reason;
- UTC occurrence time.

Invalid transitions, no-op transitions, stale versions, and malformed blocked-state metadata fail before persistent state changes.

## PLAN-ARCH-004:SEC-05 Persistence ports and authority boundaries

PostgreSQL remains the selected production transactional authority behind internal repository ports. The production schema stores project manifests, project state, task state, immutable transitions, requirements, normalized links, catalog imports, and mutation audit records.

SQLite is the deterministic local execution profile. It uses the same domain entities, migration identifiers, state-transition rules, revision semantics, and traceability behavior. Local runtime state defaults beneath `.local/` and is excluded from permanent manifests and archives.

During this stage:

- validated JSON/JSONL registries remain source authority;
- the database is an executable projection and transactional work surface;
- proposed changes may be exported for review;
- the database never silently overwrites authoritative repository catalogs;
- no live PostgreSQL verification is claimed without a configured server and credentials.

## PLAN-ARCH-004:SEC-06 Migration lifecycle and rollback

`database/MIGRATION_CATALOG.json` is the migration authority. Each ordered migration records dependencies, compatibility phase, reversibility, dialect-specific paths, and SHA-256 digests.

Migration execution must provide:

- contiguous deterministic order;
- dependency closure;
- one atomic transaction per migration;
- idempotent reapplication;
- reverse-order rollback;
- no applied record after a failed transaction;
- digest validation against committed SQL;
- SQLite behavioral verification;
- PostgreSQL DDL parity without unverified live-runtime claims.

Production activation additionally requires pre-migration backup, restore readiness, compatibility verification, controlled application, and post-migration evidence.

## PLAN-ARCH-004:SEC-07 Transactional traceability service

The traceability service imports the strict requirement catalog transactionally and normalizes every relationship into a typed link. It supports:

- requirement-to-source, plan, section, Jira, implementation, test, evidence, decision, open-decision, and evolution traversal;
- source-to-requirement traversal;
- arbitrary target-to-requirement traversal by link type;
- catalog digest and import identity;
- persisted-versus-authoritative equivalence verification;
- deterministic projection export.

A traceability mutation includes requirement ID, add/remove operation, link type, target, expected revision, actor, correlation ID, and reason. Changed mutations increment the requirement revision exactly once. Semantic no-ops preserve the revision. Stale revisions fail closed. All accepted attempts receive immutable audit records and `PROPOSED_CHANGE` authority.

## PLAN-ARCH-004:SEC-08 CLI and operator inspection

The CLI exposes bounded local operations:

- `state init` compiles the domain manifest, project state, Jira task state, and requirement traceability into the local store;
- `state status|project|task|migrations` provides machine-readable inspection;
- `state transition-project|transition-task` applies version-checked state changes;
- `trace-store init|status|requirement|source|target` provides bidirectional traceability inspection;
- `trace-store add|remove` records proposed mutations with optimistic concurrency;
- `trace-store export` writes a reviewable projection without replacing source authority.

The CLI rejects missing required parameters and rejects the local command surface when a PostgreSQL profile is selected but not live configured.

## PLAN-ARCH-004:SEC-09 Validation and test strategy

Verification includes:

- deterministic and type-scoped identifiers;
- strict parsing of all authoritative requirements;
- domain-manifest identity and idempotence;
- complete Jira-to-task compilation;
- valid and invalid state-transition behavior;
- migration catalog order, hashes, idempotence, rollback, and failure atomicity;
- project and task optimistic concurrency;
- immutable transition history;
- exact requirement import and equivalence;
- bidirectional traceability queries;
- changed, no-op, and stale mutation semantics;
- projection export authority boundaries;
- CLI initialization, queries, and fail-closed argument validation;
- repository self-validation and clean-archive revalidation.

## PLAN-ARCH-004:SEC-10 Evidence, recovery, and remaining boundaries

Completion evidence records test output, migration validation, state snapshots, traceability equivalence, CLI results, repository validation, and clean-archive verification with hashes.

Local recovery consists of closing the store, preserving or deleting the `.local` database as appropriate, recreating it from the committed migration catalog, and reimporting the authoritative registries. Migration rollback is dialect-specific and reverse ordered.

This bounded implementation does not claim the complete Project Control Kernel, live PostgreSQL operation, durable workflow activation, remote Jira/GitHub synchronization, scheduling, provider routing, Command Center APIs, Windows packaging, or AWS deployment. Those remain governed by later component plans and verification gates.
