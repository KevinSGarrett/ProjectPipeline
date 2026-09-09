"""Transactional fleet lifecycle journal shared by CLI and UI."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Lifecycle = Literal[
    "DISPATCHED",
    "RUNNING",
    "ACCEPTED",
    "REJECTED",
    "UNKNOWN_OUTCOME",
    "RECONCILING",
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fleet_lifecycle (
    job_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    fence TEXT NOT NULL,
    status TEXT NOT NULL,
    authority TEXT NOT NULL,
    remote_pid TEXT,
    remote_created_at_utc TEXT,
    payload_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
"""


class FleetLifecycleJournal:
    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        connection = sqlite3.connect(self.database)
        connection.executescript(SCHEMA_SQL)
        connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def publish(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(record, sort_keys=True, default=str)
        with self._lock:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    """
                    INSERT INTO fleet_lifecycle (
                        job_id, host_id, lease_id, fence, status, authority,
                        remote_pid, remote_created_at_utc, payload_json, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        status=excluded.status,
                        lease_id=excluded.lease_id,
                        fence=excluded.fence,
                        remote_pid=excluded.remote_pid,
                        remote_created_at_utc=excluded.remote_created_at_utc,
                        payload_json=excluded.payload_json,
                        updated_at_utc=excluded.updated_at_utc
                    """,
                    (
                        str(record["job_id"]),
                        str(record["host_id"]),
                        str(record.get("lease_id") or "none"),
                        str(record.get("fence") or "none"),
                        str(record["status"]),
                        str(record.get("authority") or "scheduler"),
                        record.get("remote_pid"),
                        record.get("remote_created_at_utc"),
                        payload,
                        now,
                    ),
                )
                db.commit()
            finally:
                db.close()
        return record

    def occupancy(self, *, authority: str) -> dict[str, Any]:
        if not authority:
            raise ValueError("zero_occupancy_requires_authority")
        db = self._connect()
        try:
            rows = list(db.execute("SELECT payload_json FROM fleet_lifecycle ORDER BY job_id"))
        finally:
            db.close()
        active = []
        for row in rows:
            item = json.loads(row[0])
            if item.get("status") in {"DISPATCHED", "RUNNING"}:
                active.append(item)
        if not active:
            return {
                "active_jobs": 0,
                "lease_id": "none",
                "assignment": "none",
                "fence": "none",
                "absence_authority": authority,
            }
        return {
            "active_jobs": len(active),
            "lease_id": ",".join(sorted(str(item.get("lease_id")) for item in active)),
            "assignment": ",".join(sorted(str(item.get("job_id")) for item in active)),
            "fence": ",".join(sorted(str(item.get("fence")) for item in active)),
        }

    def occupancy_by_host(self, *, authority: str) -> dict[str, dict[str, Any]]:
        if not authority:
            raise ValueError("zero_occupancy_requires_authority")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in self.snapshot():
            if item.get("status") not in {"DISPATCHED", "RUNNING"}:
                continue
            grouped.setdefault(str(item.get("host_id")), []).append(item)
        occupancy: dict[str, dict[str, Any]] = {}
        for host_id, items in grouped.items():
            occupancy[host_id] = {
                "active_jobs": len(items),
                "lease_id": ",".join(sorted(str(item.get("lease_id")) for item in items)),
                "assignment": ",".join(sorted(str(item.get("job_id")) for item in items)),
                "fence": ",".join(sorted(str(item.get("fence")) for item in items)),
                "absence_authority": authority,
            }
        return occupancy

    def snapshot(self) -> list[dict[str, Any]]:
        db = self._connect()
        try:
            rows = list(db.execute("SELECT payload_json FROM fleet_lifecycle ORDER BY job_id"))
        finally:
            db.close()
        return [json.loads(row[0]) for row in rows]
