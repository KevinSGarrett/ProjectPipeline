# Database Assets

This directory contains the versioned database migration catalog and dialect-specific SQL for Project Pipeline core state, requirement traceability, and project-intake compilation.

- `MIGRATION_CATALOG.json` is generated from SQL content and stores exact SHA-256 digests.
- `migrations/sqlite` powers deterministic local execution and tests.
- `migrations/postgresql` defines the selected production schema boundary.

Use `project-pipeline state migrations` to inspect the local profile. Use repository validation to verify catalog order, dependency closure, file existence, and digests.

- `PPDB-0003` adds persisted intake compilations and bootstrap receipts for deterministic adoption and reconciliation.
- `PPDB-0004` adds Jira remote snapshots, reconciliation plans, transactional synchronization outbox state, remote mappings, and receipts.
