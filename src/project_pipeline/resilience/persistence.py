from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from project_pipeline.domain.resilience import (
    BackupRecord,
    ExternalPreconditionIncident,
    FailoverDecision,
    MachineHealth,
    OperatingModeDecision,
    RecoveryObjective,
    RestoreVerification,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class ResilienceStore:
    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> ResilienceStore:
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("resilience store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def _save(
        self,
        table: str,
        key_col: str,
        key: str,
        payload: str,
        extras: tuple[tuple[str, object], ...] = (),
    ) -> None:
        cols = [key_col, *[k for k, _ in extras], "payload_json"]
        vals = [key, *[v for _, v in extras], payload]
        marks = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols[1:])
        with self.db:
            self.db.execute(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks}) ON CONFLICT({key_col}) DO UPDATE SET {updates}",
                vals,
            )

    def save_machine(self, v: MachineHealth) -> None:
        self._save(
            "resilience_machines",
            "machine_id",
            v.machine_id,
            v.model_dump_json(),
            (
                ("healthy", int(v.healthy)),
                ("heartbeat_at_utc", v.heartbeat_at_utc.isoformat()),
                ("fencing_token", v.fencing_token),
            ),
        )

    def save_failover(self, v: FailoverDecision) -> None:
        self._save(
            "resilience_failover_decisions",
            "decision_id",
            v.decision_id,
            v.model_dump_json(),
            (("eligible", int(v.eligible)), ("decided_at_utc", v.decided_at_utc.isoformat())),
        )

    def save_mode(self, v: OperatingModeDecision) -> None:
        self._save(
            "resilience_operating_modes",
            "decision_id",
            v.decision_id,
            v.model_dump_json(),
            (("mode", v.mode.value), ("decided_at_utc", v.decided_at_utc.isoformat())),
        )

    def save_incident(self, v: ExternalPreconditionIncident) -> None:
        self._save(
            "resilience_incidents",
            "incident_id",
            v.incident_id,
            v.model_dump_json(),
            (
                ("failure_domain", v.failure_domain.value),
                ("created_at_utc", v.created_at_utc.isoformat()),
            ),
        )

    def save_objective(self, v: RecoveryObjective) -> None:
        self._save(
            "resilience_recovery_objectives",
            "objective_id",
            v.objective_id,
            v.model_dump_json(),
            (("domain", v.domain), ("rpo_seconds", v.rpo_seconds), ("rto_seconds", v.rto_seconds)),
        )

    def save_backup(self, v: BackupRecord) -> None:
        self._save(
            "resilience_backups",
            "backup_id",
            v.backup_id,
            v.model_dump_json(),
            (
                ("domain", v.domain),
                ("completed", int(v.completed)),
                ("created_at_utc", v.created_at_utc.isoformat()),
            ),
        )

    def save_restore(self, v: RestoreVerification) -> None:
        self._save(
            "resilience_restore_verifications",
            "restore_id",
            v.restore_id,
            v.model_dump_json(),
            (
                ("backup_id", v.backup_id),
                ("state", v.state.value),
                ("verified_at_utc", v.verified_at_utc.isoformat()),
            ),
        )

    def status(self) -> dict[str, int]:
        tables = (
            "resilience_machines",
            "resilience_failover_decisions",
            "resilience_operating_modes",
            "resilience_incidents",
            "resilience_recovery_objectives",
            "resilience_backups",
            "resilience_restore_verifications",
        )
        return {t: int(self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in tables}
