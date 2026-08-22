from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from project_pipeline.domain.verification import (
    GoldenJourneyResult,
    VerificationArtifact,
    VerificationRun,
    VerificationToolActivation,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class VerificationStore:
    """Persistent verification-run, tool-activation, journey, and artifact state."""

    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> VerificationStore:
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
            raise RuntimeError("verification store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def save_activation(self, project_id: str, value: VerificationToolActivation) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT INTO verification_tool_activations
                    (activation_id, project_id, upstream_id, state, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(activation_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    upstream_id=excluded.upstream_id,
                    state=excluded.state,
                    payload_json=excluded.payload_json
                """,
                (
                    value.activation_id,
                    project_id,
                    value.upstream_id,
                    value.state.value,
                    value.model_dump_json(),
                ),
            )

    def list_activations(self, project_id: str) -> tuple[VerificationToolActivation, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM verification_tool_activations WHERE project_id=? ORDER BY upstream_id",
            (project_id,),
        ).fetchall()
        return tuple(VerificationToolActivation.model_validate_json(row[0]) for row in rows)

    def save_run(self, value: VerificationRun) -> None:
        with self.db:
            existing = self.db.execute(
                "SELECT payload_json FROM verification_runs WHERE run_id=?", (value.run_id,)
            ).fetchone()
            if existing is not None:
                prior = VerificationRun.model_validate_json(existing[0])
                if prior != value:
                    raise ValueError(f"verification run identity collision: {value.run_id}")
                return
            self.db.execute(
                """
                INSERT INTO verification_runs
                    (run_id, project_id, profile, final_state, payload_json, completed_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    value.run_id,
                    value.project_id,
                    value.profile,
                    value.final_state.value,
                    value.model_dump_json(),
                    value.completed_at_utc.isoformat(),
                ),
            )
            for result in value.results:
                self.db.execute(
                    """
                    INSERT INTO verification_check_results
                        (run_id, check_id, category, state, required, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        value.run_id,
                        result.check_id,
                        result.category.value,
                        result.state.value,
                        1 if result.required else 0,
                        result.model_dump_json(),
                    ),
                )
                for artifact in result.artifacts:
                    self.save_artifact(artifact, run_id=value.run_id)

    def save_artifact(self, value: VerificationArtifact, *, run_id: str) -> None:
        self.db.execute(
            """
            INSERT INTO verification_artifacts
                (artifact_id, run_id, check_id, kind, relative_path, sha256, size_bytes, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO NOTHING
            """,
            (
                value.artifact_id,
                run_id,
                value.produced_by_check_id,
                value.kind.value,
                value.relative_path,
                value.sha256,
                value.size_bytes,
                value.model_dump_json(),
            ),
        )

    def save_journey(self, project_id: str, value: GoldenJourneyResult) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT INTO verification_golden_journey_results
                    (result_id, project_id, journey_id, state, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(result_id) DO NOTHING
                """,
                (
                    value.result_id,
                    project_id,
                    value.journey_id,
                    value.state.value,
                    value.model_dump_json(),
                ),
            )

    def latest_run(self, project_id: str) -> VerificationRun | None:
        row = self.db.execute(
            """
            SELECT payload_json FROM verification_runs
            WHERE project_id=? ORDER BY completed_at_utc DESC, run_id DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return None if row is None else VerificationRun.model_validate_json(row[0])

    def status(self, project_id: str) -> dict[str, int | str | None]:
        def count(table: str) -> int:
            row = self.db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)
            ).fetchone()
            return int(row[0])

        latest = self.latest_run(project_id)
        return {
            "tool_activation_count": count("verification_tool_activations"),
            "run_count": count("verification_runs"),
            "golden_journey_result_count": count("verification_golden_journey_results"),
            "latest_run_id": None if latest is None else latest.run_id,
            "latest_run_state": None if latest is None else latest.final_state.value,
        }
