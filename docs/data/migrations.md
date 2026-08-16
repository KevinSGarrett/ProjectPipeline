# Database Migration Lifecycle

`database/MIGRATION_CATALOG.json` defines ordered, reversible migration records for SQLite and PostgreSQL. Every SQL file is referenced by a SHA-256 digest.

Current migrations:

1. `PPDB-0001` — project, project-state, task-state, transition, and system-metadata foundation.
2. `PPDB-0002` — requirement, traceability-link, catalog-import, and mutation-audit foundation.
3. `PPDB-0003` — project-intake compilation and bootstrap-receipt foundation.

## Safety properties

- Migration identifiers and sequences are unique and contiguous.
- Dependencies must refer only to earlier migrations.
- Every reversible migration must provide down SQL for both dialects.
- Catalog validation detects missing or changed SQL.
- SQLite executes one immediate transaction per migration.
- Failure rolls back that migration without falsely recording it as applied.
- Rollback occurs in reverse order.
- Applying an already applied catalog is idempotent.

Production migration activation additionally requires a pre-migration backup, restore path, compatibility verification, and post-migration checks.
