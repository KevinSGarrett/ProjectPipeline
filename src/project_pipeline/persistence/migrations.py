from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel
from project_pipeline.domain.identifiers import IdentifierKind, validate_identifier
from project_pipeline.io import read_json, sha256_file, write_json


class MigrationError(RuntimeError):
    """Raised when a database migration cannot be applied or reversed safely."""


class MigrationRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    migration_id: str
    sequence: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    depends_on: tuple[str, ...] = ()
    reversible: bool
    compatibility_phase: Literal["EXPAND", "MIGRATE", "VERIFY", "CONTRACT"]
    sqlite_up_path: str
    sqlite_up_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sqlite_down_path: str | None = None
    sqlite_down_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    postgresql_up_path: str
    postgresql_up_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    postgresql_down_path: str | None = None
    postgresql_down_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("migration_id")
    @classmethod
    def validate_migration_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.MIGRATION)

    @field_validator("depends_on")
    @classmethod
    def validate_dependencies(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("migration dependencies cannot contain duplicates")
        for value in values:
            validate_identifier(value, IdentifierKind.MIGRATION)
        return values

    @model_validator(mode="after")
    def validate_rollback_metadata(self) -> MigrationRecord:
        pairs = (
            (self.sqlite_down_path, self.sqlite_down_sha256),
            (self.postgresql_down_path, self.postgresql_down_sha256),
        )
        for path, digest in pairs:
            if bool(path) != bool(digest):
                raise ValueError("migration rollback path and digest must be provided together")
        if self.reversible and any(not path for path, _ in pairs):
            raise ValueError("reversible migrations require rollback SQL for every dialect")
        return self


class MigrationCatalog(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    catalog_id: Literal["PROJECT-PIPELINE-DATABASE-MIGRATIONS"] = (
        "PROJECT-PIPELINE-DATABASE-MIGRATIONS"
    )
    migrations: tuple[MigrationRecord, ...]

    @model_validator(mode="after")
    def validate_order(self) -> MigrationCatalog:
        identifiers = [item.migration_id for item in self.migrations]
        sequences = [item.sequence for item in self.migrations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("migration identifiers must be unique")
        if sequences != sorted(sequences) or sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("migration sequences must be contiguous and ordered")
        seen: set[str] = set()
        for item in self.migrations:
            if any(dependency not in seen for dependency in item.depends_on):
                raise ValueError(
                    f"migration {item.migration_id} depends on an unknown or later migration"
                )
            seen.add(item.migration_id)
        return self


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    applied: tuple[str, ...]
    pending: tuple[str, ...]
    latest_available: str | None
    latest_applied: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "applied": list(self.applied),
            "pending": list(self.pending),
            "latest_available": self.latest_available,
            "latest_applied": self.latest_applied,
        }


def _catalog_path(root: Path) -> Path:
    return root / "database" / "MIGRATION_CATALOG.json"


def load_migration_catalog(root: Path) -> MigrationCatalog:
    return MigrationCatalog.model_validate(read_json(_catalog_path(root)))


def _record(
    root: Path,
    *,
    migration_id: str,
    sequence: int,
    name: str,
    depends_on: tuple[str, ...],
    reversible: bool,
    compatibility_phase: Literal["EXPAND", "MIGRATE", "VERIFY", "CONTRACT"],
) -> MigrationRecord:
    base = f"{migration_id}_{name}"
    sqlite_up = f"database/migrations/sqlite/{base}.up.sql"
    sqlite_down = f"database/migrations/sqlite/{base}.down.sql"
    postgres_up = f"database/migrations/postgresql/{base}.up.sql"
    postgres_down = f"database/migrations/postgresql/{base}.down.sql"
    return MigrationRecord(
        migration_id=migration_id,
        sequence=sequence,
        name=name,
        depends_on=depends_on,
        reversible=reversible,
        compatibility_phase=compatibility_phase,
        sqlite_up_path=sqlite_up,
        sqlite_up_sha256=sha256_file(root / sqlite_up),
        sqlite_down_path=sqlite_down if reversible else None,
        sqlite_down_sha256=sha256_file(root / sqlite_down) if reversible else None,
        postgresql_up_path=postgres_up,
        postgresql_up_sha256=sha256_file(root / postgres_up),
        postgresql_down_path=postgres_down if reversible else None,
        postgresql_down_sha256=sha256_file(root / postgres_down) if reversible else None,
    )


def write_migration_catalog(root: Path) -> MigrationCatalog:
    catalog = MigrationCatalog(
        migrations=(
            _record(
                root,
                migration_id="PPDB-0001",
                sequence=1,
                name="core_state",
                depends_on=(),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0002",
                sequence=2,
                name="requirement_traceability",
                depends_on=("PPDB-0001",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0003",
                sequence=3,
                name="project_intake_compilation",
                depends_on=("PPDB-0002",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0004",
                sequence=4,
                name="jira_steward_sync",
                depends_on=("PPDB-0003",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0005",
                sequence=5,
                name="repository_github_stewardship",
                depends_on=("PPDB-0004",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0006",
                sequence=6,
                name="project_control_sequencing",
                depends_on=("PPDB-0005",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0007",
                sequence=7,
                name="dynamic_scheduler_resources",
                depends_on=("PPDB-0006",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0008",
                sequence=8,
                name="agent_router_provider_state",
                depends_on=("PPDB-0007",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0009",
                sequence=9,
                name="context_delegation",
                depends_on=("PPDB-0008",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0010",
                sequence=10,
                name="durable_orchestration_recovery",
                depends_on=("PPDB-0009",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0011",
                sequence=11,
                name="budget_governor",
                depends_on=("PPDB-0010",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0012",
                sequence=12,
                name="execution_assurance_completion_gate",
                depends_on=("PPDB-0011",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0013",
                sequence=13,
                name="verification_harness",
                depends_on=("PPDB-0012",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0014",
                sequence=14,
                name="security_identity_policy_secrets_supply_chain",
                depends_on=("PPDB-0013",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0015",
                sequence=15,
                name="resilience_recovery_local_runtime",
                depends_on=("PPDB-0014",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0016",
                sequence=16,
                name="command_center_realtime",
                depends_on=("PPDB-0015",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0017",
                sequence=17,
                name="director_incident_notifications",
                depends_on=("PPDB-0016",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0018",
                sequence=18,
                name="advanced_platform_lifecycle",
                depends_on=("PPDB-0017",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
            _record(
                root,
                migration_id="PPDB-0019",
                sequence=19,
                name="audit_immutability",
                depends_on=("PPDB-0018",),
                reversible=True,
                compatibility_phase="VERIFY",
            ),
            _record(
                root,
                migration_id="PPDB-0020",
                sequence=20,
                name="autonomy_runtime_supervisor",
                depends_on=("PPDB-0019",),
                reversible=True,
                compatibility_phase="EXPAND",
            ),
        )
    )
    write_json(_catalog_path(root), catalog.model_dump(mode="json"))
    return catalog


def validate_migration_catalog(root: Path) -> list[str]:
    errors: list[str] = []
    path = _catalog_path(root)
    if not path.exists():
        return ["database/MIGRATION_CATALOG.json is missing"]
    try:
        catalog = load_migration_catalog(root)
    except Exception as error:
        return [f"migration catalog is invalid: {error}"]
    for migration in catalog.migrations:
        paths = (
            (migration.sqlite_up_path, migration.sqlite_up_sha256),
            (migration.sqlite_down_path, migration.sqlite_down_sha256),
            (migration.postgresql_up_path, migration.postgresql_up_sha256),
            (migration.postgresql_down_path, migration.postgresql_down_sha256),
        )
        for relative, expected in paths:
            if relative is None:
                continue
            file = root / relative
            if not file.exists():
                errors.append(f"migration file is missing: {relative}")
            elif sha256_file(file) != expected:
                errors.append(f"migration digest is stale: {relative}")
    return errors


def _split_sql(text: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    trigger_mode = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if not buffer and stripped.upper().startswith("CREATE TRIGGER"):
            trigger_mode = True
        buffer.append(line)
        if trigger_mode:
            # SQLite trigger bodies contain semicolons before the final END;. Treat the
            # complete CREATE TRIGGER ... BEGIN ... END; block as one migration statement.
            if stripped.upper() == "END;":
                statement = "\n".join(buffer).strip()
                statements.append(statement[:-1].strip())
                buffer = []
                trigger_mode = False
        elif stripped.endswith(";"):
            statement = "\n".join(buffer).strip()
            statements.append(statement[:-1].strip())
            buffer = []
    if buffer:
        raise MigrationError("SQL migration contains a statement without a terminating semicolon")
    return statements


class SQLiteMigrationRunner:
    """Apply reversible migrations with one transaction per migration."""

    def __init__(self, connection: sqlite3.Connection, root: Path) -> None:
        self.connection = connection
        self.root = root.resolve()
        self.catalog = load_migration_catalog(self.root)
        self._ensure_control_table()

    def _ensure_control_table(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                sql_sha256 TEXT NOT NULL,
                applied_at_utc TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def applied(self) -> tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY sequence"
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def status(self) -> MigrationStatus:
        applied = self.applied()
        available = tuple(item.migration_id for item in self.catalog.migrations)
        pending = tuple(item for item in available if item not in set(applied))
        return MigrationStatus(
            applied=applied,
            pending=pending,
            latest_available=available[-1] if available else None,
            latest_applied=applied[-1] if applied else None,
        )

    def apply_all(self, *, target: str | None = None) -> MigrationStatus:
        applied = set(self.applied())
        for migration in self.catalog.migrations:
            if migration.migration_id in applied:
                if target == migration.migration_id:
                    break
                continue
            if any(dependency not in applied for dependency in migration.depends_on):
                raise MigrationError(
                    f"migration dependency is not applied: {migration.migration_id}"
                )
            self._apply(migration)
            applied.add(migration.migration_id)
            if target == migration.migration_id:
                break
        if target is not None and target not in applied:
            raise MigrationError(f"unknown migration target: {target}")
        return self.status()

    def _apply(self, migration: MigrationRecord) -> None:
        text = (self.root / migration.sqlite_up_path).read_text(encoding="utf-8")
        timestamp = datetime.now(UTC).isoformat()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            for statement in _split_sql(text):
                self.connection.execute(statement)
            self.connection.execute(
                """
                INSERT INTO schema_migrations
                    (migration_id, sequence, name, sql_sha256, applied_at_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    migration.migration_id,
                    migration.sequence,
                    migration.name,
                    migration.sqlite_up_sha256,
                    timestamp,
                ),
            )
            self.connection.commit()
        except Exception as error:
            self.connection.rollback()
            raise MigrationError(f"migration {migration.migration_id} failed: {error}") from error

    def rollback_last(self) -> MigrationStatus:
        applied = self.applied()
        if not applied:
            return self.status()
        migration_id = applied[-1]
        migration = next(
            item for item in self.catalog.migrations if item.migration_id == migration_id
        )
        if not migration.reversible or migration.sqlite_down_path is None:
            raise MigrationError(f"migration is not reversible: {migration_id}")
        text = (self.root / migration.sqlite_down_path).read_text(encoding="utf-8")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            for statement in _split_sql(text):
                self.connection.execute(statement)
            self.connection.execute(
                "DELETE FROM schema_migrations WHERE migration_id = ?", (migration_id,)
            )
            self.connection.commit()
        except Exception as error:
            self.connection.rollback()
            raise MigrationError(f"rollback {migration_id} failed: {error}") from error
        return self.status()


def migration_catalog_fingerprint(root: Path) -> str:
    payload = json.dumps(
        load_migration_catalog(root).model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
