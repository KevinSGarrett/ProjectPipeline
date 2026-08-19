from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, TypeVar

from project_pipeline.observability.ops_models import (
    DEFAULT_RETENTION_DAYS,
    CacheEvent,
    CostSample,
    DistilledMemory,
    HealthLayerObservation,
    WorkerRunRecord,
    canonical_payload,
)


class _Dumpable(Protocol):
    def model_dump(self, *, mode: str) -> object: ...


T = TypeVar("T", bound=_Dumpable)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ops_records (
    record_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    superseded_by TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ops_records_kind_time
    ON ops_records(kind, recorded_at_utc);
CREATE TABLE IF NOT EXISTS ops_journal (
    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);
"""


class OpsStoreError(ValueError):
    """Raised when an operations record cannot be stored or replayed safely."""


class OpsIntelligenceStore:
    """Out-of-tree operations telemetry. Records are immutable after insert."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._connect(self._connection()).executescript(SCHEMA_SQL)
        self.replay_journal()

    @classmethod
    def open(cls, root: Path) -> OpsIntelligenceStore:
        root = root.resolve()
        return cls(root / ".local" / "state" / "ops_intelligence" / "ops.sqlite3")

    def _connection(self) -> sqlite3.Connection:
        existing = getattr(self._local, "db", None)
        if isinstance(existing, sqlite3.Connection):
            return existing
        connection = sqlite3.connect(
            self.database,
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        self._local.db = connection
        return connection

    def _connect(self, connection: sqlite3.Connection) -> sqlite3.Connection:
        return connection

    def close(self) -> None:
        with self._lock:
            connection = getattr(self._local, "db", None)
            if connection is not None:
                connection.close()
                self._local.db = None

    def put_layer(self, observation: HealthLayerObservation) -> HealthLayerObservation:
        return self._put(
            "layer", observation.observation_id, observation, observation.recorded_at_utc
        )

    def put_worker(self, record: WorkerRunRecord) -> WorkerRunRecord:
        return self._put("worker", record.run_id, record, record.recorded_at_utc)

    def put_cost(self, sample: CostSample) -> CostSample:
        return self._put("cost", sample.sample_id, sample, sample.recorded_at_utc)

    def put_cache(self, event: CacheEvent) -> CacheEvent:
        return self._put("cache", event.event_id, event, event.recorded_at_utc)

    def put_memory(self, memory: DistilledMemory) -> DistilledMemory:
        return self._put("memory", memory.memory_id, memory, memory.recorded_at_utc)

    def _put(self, kind: str, record_id: str, model: T, recorded_at: datetime) -> T:
        payload = canonical_payload(model.model_dump(mode="json"))
        now = datetime.now(UTC).isoformat()
        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT payload_json FROM ops_records WHERE record_id = ?",
                    (record_id,),
                ).fetchone()
                if existing is not None:
                    if existing["payload_json"] != payload:
                        raise OpsStoreError(f"conflicting replay for {record_id}")
                    db.execute("COMMIT")
                    return model
                db.execute(
                    """
                    INSERT INTO ops_journal(record_id, kind, operation, payload_json, recorded_at_utc)
                    VALUES (?, ?, 'put', ?, ?)
                    """,
                    (record_id, kind, payload, now),
                )
                db.execute(
                    """
                    INSERT INTO ops_records(record_id, kind, recorded_at_utc, superseded_by, payload_json)
                    VALUES (?, ?, ?, NULL, ?)
                    """,
                    (record_id, kind, recorded_at.astimezone(UTC).isoformat(), payload),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return model

    def replay_journal(self) -> int:
        with self._lock:
            db = self._connection()
            rows = db.execute(
                "SELECT record_id, kind, payload_json, operation FROM ops_journal ORDER BY journal_id"
            ).fetchall()
            restored = 0
            for row in rows:
                if row["operation"] != "put":
                    continue
                existing = db.execute(
                    "SELECT payload_json FROM ops_records WHERE record_id = ?",
                    (row["record_id"],),
                ).fetchone()
                if existing is None:
                    payload = row["payload_json"]
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        db.execute(
                            """
                            INSERT INTO ops_records(record_id, kind, recorded_at_utc, superseded_by, payload_json)
                            VALUES (?, ?, ?, NULL, ?)
                            """,
                            (
                                row["record_id"],
                                row["kind"],
                                datetime.now(UTC).isoformat(),
                                payload,
                            ),
                        )
                        db.execute("COMMIT")
                    except Exception:
                        db.execute("ROLLBACK")
                        raise
                    restored += 1
                elif existing["payload_json"] != row["payload_json"]:
                    raise OpsStoreError(f"journal conflicts with store for {row['record_id']}")
            return restored

    def list_kind(self, kind: str) -> list[dict[str, object]]:
        with self._lock:
            db = self._connection()
            rows = db.execute(
                """
                SELECT record_id, kind, recorded_at_utc, payload_json
                FROM ops_records
                WHERE kind = ? AND superseded_by IS NULL
                ORDER BY recorded_at_utc ASC, record_id ASC
                """,
                (kind,),
            ).fetchall()
        return [dict(row) for row in rows]

    def apply_retention(self, *, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        cutoff_text = cutoff.isoformat()
        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            try:
                deleted = db.execute(
                    "DELETE FROM ops_records WHERE recorded_at_utc < ?",
                    (cutoff_text,),
                ).rowcount
                db.execute(
                    """
                    INSERT INTO ops_journal(record_id, kind, operation, payload_json, recorded_at_utc)
                    VALUES (?, 'meta', 'retain', ?, ?)
                    """,
                    ("RETENTION", cutoff_text, datetime.now(UTC).isoformat()),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return int(deleted or 0)
