from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from project_pipeline.domain.control import ControlSnapshot
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class ControlStore:
    """Persistent projection store for deterministic control evaluations."""

    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> ControlStore:
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.initialize()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("control store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def save_snapshot(self, snapshot: ControlSnapshot) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO control_snapshots
                (snapshot_id, project_id, graph_fingerprint, snapshot_fingerprint,
                 ready_count, active_count, blocked_count, scope_finding_count,
                 completion_state, payload_json, created_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.project_id,
                snapshot.sequence.graph_fingerprint,
                snapshot.snapshot_fingerprint,
                snapshot.sequence.ready_count,
                snapshot.sequence.active_count,
                snapshot.sequence.blocked_count,
                len(snapshot.scope.findings),
                snapshot.completion.state.value,
                snapshot.model_dump_json(),
                snapshot.generated_at_utc.isoformat(),
            ),
        )
        self.db.execute(
            "DELETE FROM control_sequence_items WHERE snapshot_id=?", (snapshot.snapshot_id,)
        )
        for item in snapshot.sequence.ordered_ready_work:
            self.db.execute(
                """
                INSERT INTO control_sequence_items
                    (snapshot_id, rank, task_id, readiness, total_score, on_critical_path, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    item.rank,
                    item.task_id,
                    item.readiness.value,
                    item.score.total_score,
                    int(item.on_critical_path),
                    item.model_dump_json(),
                ),
            )
        self.db.execute(
            "DELETE FROM control_scope_findings WHERE snapshot_id=?", (snapshot.snapshot_id,)
        )
        for index, finding in enumerate(snapshot.scope.findings, start=1):
            self.db.execute(
                """
                INSERT INTO control_scope_findings
                    (snapshot_id, finding_order, kind, subject_id, related_id, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    index,
                    finding.kind.value,
                    finding.subject_id,
                    finding.related_id,
                    finding.model_dump_json(),
                ),
            )
        self.db.commit()

    def get_snapshot(self, snapshot_id: str) -> ControlSnapshot | None:
        row = self.db.execute(
            "SELECT payload_json FROM control_snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
        return None if row is None else ControlSnapshot.model_validate_json(row[0])

    def latest_snapshot(self, project_id: str) -> ControlSnapshot | None:
        row = self.db.execute(
            """
            SELECT payload_json FROM control_snapshots
            WHERE project_id=? ORDER BY created_at_utc DESC, snapshot_id DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return None if row is None else ControlSnapshot.model_validate_json(row[0])

    def status(self, project_id: str) -> dict[str, Any]:
        row = self.db.execute(
            """
            SELECT COUNT(*) AS count, MAX(created_at_utc) AS latest
            FROM control_snapshots WHERE project_id=?
            """,
            (project_id,),
        ).fetchone()
        latest = self.latest_snapshot(project_id)
        return {
            "schema_version": "1.0.0",
            "project_id": project_id,
            "snapshot_count": int(row["count"]),
            "latest_snapshot_at_utc": row["latest"],
            "latest_snapshot_id": latest.snapshot_id if latest else None,
            "ready_count": latest.sequence.ready_count if latest else 0,
            "completion_state": latest.completion.state.value if latest else None,
            "scope_finding_count": len(latest.scope.findings) if latest else 0,
        }
