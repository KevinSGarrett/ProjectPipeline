from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from project_pipeline.domain.evidence_observation import EvidenceObservation

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS evidence_observations (
    observation_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    subject_sha TEXT NOT NULL,
    subject_tree TEXT NOT NULL,
    acceptance_scope_fingerprint TEXT NOT NULL,
    result TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    superseded_by TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_observations_lookup
    ON evidence_observations(evidence_id, subject_sha, subject_tree, recorded_at_utc);
CREATE TABLE IF NOT EXISTS evidence_observation_journal (
    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);
"""


class ObservationStoreError(ValueError):
    """Raised when an observation cannot be recorded or replayed safely."""


class EvidenceObservationStore:
    """Immutable observation receipts stored outside the subject Git tree."""

    def __init__(self, database: Path, *, archive_dir: Path | None = None) -> None:
        self.database = database
        self.archive_dir = archive_dir or database.parent / "observations"
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.database, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA_SQL)
        self._db.commit()
        self.replay_journal()

    @classmethod
    def open(cls, root: Path) -> EvidenceObservationStore:
        root = root.resolve()
        base = root / ".local" / "state" / "evidence"
        return cls(base / "observations.sqlite3", archive_dir=base / "observations")

    def close(self) -> None:
        self._db.close()

    def put(self, observation: EvidenceObservation) -> EvidenceObservation:
        payload = json.dumps(
            observation.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                existing = self._db.execute(
                    "SELECT payload_json FROM evidence_observations WHERE observation_id = ?",
                    (observation.observation_id,),
                ).fetchone()
                if existing is not None:
                    if existing["payload_json"] != payload:
                        raise ObservationStoreError(
                            f"conflicting replay for observation {observation.observation_id}"
                        )
                    self._db.execute("COMMIT")
                    return observation
                self._db.execute(
                    """
                    INSERT INTO evidence_observation_journal(
                        observation_id, operation, payload_json, recorded_at_utc
                    ) VALUES (?, 'put', ?, ?)
                    """,
                    (observation.observation_id, payload, now),
                )
                if observation.supersedes:
                    self._db.execute(
                        """
                        UPDATE evidence_observations
                        SET superseded_by = ?
                        WHERE observation_id = ? AND superseded_by IS NULL
                        """,
                        (observation.observation_id, observation.supersedes),
                    )
                self._db.execute(
                    """
                    INSERT INTO evidence_observations(
                        observation_id, evidence_id, subject_sha, subject_tree,
                        acceptance_scope_fingerprint, result, recorded_at_utc,
                        superseded_by, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        observation.observation_id,
                        observation.evidence_id,
                        observation.integrated_sha,
                        observation.integrated_tree,
                        observation.acceptance_scope_fingerprint,
                        observation.result.value,
                        observation.recorded_at_utc.isoformat(),
                        payload,
                    ),
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        archive = self.archive_dir / f"{observation.observation_id}.json"
        archive.write_text(payload + "\n", encoding="utf-8", newline="\n")
        return observation

    def get(self, observation_id: str) -> EvidenceObservation | None:
        row = self._db.execute(
            "SELECT payload_json FROM evidence_observations WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        return EvidenceObservation.model_validate_json(row["payload_json"]) if row else None

    def list_for_evidence(self, evidence_id: str) -> tuple[EvidenceObservation, ...]:
        rows = self._db.execute(
            """
            SELECT payload_json FROM evidence_observations
            WHERE evidence_id = ?
            ORDER BY recorded_at_utc ASC, observation_id ASC
            """,
            (evidence_id,),
        ).fetchall()
        return tuple(EvidenceObservation.model_validate_json(row["payload_json"]) for row in rows)

    def current(
        self,
        evidence_id: str,
        *,
        subject_sha: str | None = None,
        subject_tree: str | None = None,
    ) -> EvidenceObservation | None:
        clauses = ["evidence_id = ?", "superseded_by IS NULL"]
        values: list[Any] = [evidence_id]
        if subject_sha:
            clauses.append("subject_sha = ?")
            values.append(subject_sha.lower())
        if subject_tree:
            clauses.append("subject_tree = ?")
            values.append(subject_tree.lower())
        row = self._db.execute(
            f"""
            SELECT payload_json FROM evidence_observations
            WHERE {" AND ".join(clauses)}
            ORDER BY recorded_at_utc DESC, observation_id DESC
            LIMIT 1
            """,
            values,
        ).fetchone()
        return EvidenceObservation.model_validate_json(row["payload_json"]) if row else None

    def latest_any(self, evidence_id: str) -> EvidenceObservation | None:
        row = self._db.execute(
            """
            SELECT payload_json FROM evidence_observations
            WHERE evidence_id = ?
            ORDER BY recorded_at_utc DESC, observation_id DESC
            LIMIT 1
            """,
            (evidence_id,),
        ).fetchone()
        return EvidenceObservation.model_validate_json(row["payload_json"]) if row else None

    def replay_journal(self) -> int:
        restored = 0
        rows = self._db.execute(
            """
            SELECT observation_id, payload_json FROM evidence_observation_journal
            WHERE operation = 'put'
            ORDER BY journal_id ASC
            """
        ).fetchall()
        for row in rows:
            existing = self._db.execute(
                "SELECT payload_json FROM evidence_observations WHERE observation_id = ?",
                (row["observation_id"],),
            ).fetchone()
            if existing is None:
                observation = EvidenceObservation.model_validate_json(row["payload_json"])
                self._db.execute(
                    """
                    INSERT INTO evidence_observations(
                        observation_id, evidence_id, subject_sha, subject_tree,
                        acceptance_scope_fingerprint, result, recorded_at_utc,
                        superseded_by, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        observation.observation_id,
                        observation.evidence_id,
                        observation.integrated_sha,
                        observation.integrated_tree,
                        observation.acceptance_scope_fingerprint,
                        observation.result.value,
                        observation.recorded_at_utc.isoformat(),
                        row["payload_json"],
                    ),
                )
                restored += 1
            elif existing["payload_json"] != row["payload_json"]:
                raise ObservationStoreError(
                    f"conflicting replay for observation {row['observation_id']}"
                )
        if restored:
            self._db.commit()
        return restored

    def retain(self, *, keep_current: bool = True, max_age_seconds: int | None = None) -> int:
        cutoff = None
        if max_age_seconds is not None:
            cutoff = (datetime.now(UTC) - timedelta(seconds=max_age_seconds)).isoformat()
        query = "SELECT observation_id, payload_json, superseded_by, recorded_at_utc FROM evidence_observations"
        removed = 0
        for row in self._db.execute(query).fetchall():
            if keep_current and row["superseded_by"] is None:
                continue
            if cutoff is None or row["recorded_at_utc"] <= cutoff:
                self._db.execute(
                    "DELETE FROM evidence_observations WHERE observation_id = ?",
                    (row["observation_id"],),
                )
                archive = self.archive_dir / f"{row['observation_id']}.json"
                if archive.exists():
                    archive.unlink()
                removed += 1
        if removed:
            self._db.commit()
        return removed

    def status(self) -> dict[str, int]:
        current = self._db.execute(
            "SELECT COUNT(*) FROM evidence_observations WHERE superseded_by IS NULL"
        ).fetchone()[0]
        total = self._db.execute("SELECT COUNT(*) FROM evidence_observations").fetchone()[0]
        return {"observations": int(total), "current": int(current)}
