# Persistence Profiles

## Production authority

PostgreSQL is the selected production transactional authority behind Project Pipeline repository ports. PostgreSQL DDL is maintained for project state, task state, immutable transitions, typed requirements, traceability links, catalog imports, mutation audit records, project-intake compilations, and bootstrap receipts. Live PostgreSQL behavior is not claimed until a configured server and credentials are available for integration verification.

## Deterministic local profile

SQLite is the executable local profile. It uses the same semantic entities and migration identifiers as PostgreSQL and supports:

- atomic migration application and rollback;
- project-manifest persistence;
- project and task state with optimistic concurrency;
- immutable transition history;
- authoritative requirement-catalog import;
- bidirectional traceability queries;
- proposed traceability mutations with revision checks;
- deterministic projection export;
- machine-readable state snapshots;
- deterministic project-intake compilation and bootstrap-receipt persistence.

Runtime state defaults to `.local/state/project_pipeline.db`. `.local` is excluded from repository manifests and permanent archives.

## Authority boundary

The validated JSON/JSONL registries remain the source authority during this migration stage. Database rows are an executable projection and transactional work surface. Proposed changes are exported for controlled review; they never overwrite the authoritative requirement catalog automatically.
