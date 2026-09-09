"""Durable dispatch intents and exactly-once result identity."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from project_pipeline.autonomy_runtime.providers import contains_secret_shaped

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fleet_dispatch_intents (
    job_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    fence TEXT NOT NULL,
    source_sha TEXT NOT NULL,
    source_tree TEXT NOT NULL,
    overlay_sha256 TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    principal TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    deadline_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fleet_job_results (
    job_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    fence TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    output_sha256 TEXT NOT NULL,
    stdout_sha256 TEXT NOT NULL,
    stderr_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    accepted_at_utc TEXT
);
CREATE TABLE IF NOT EXISTS fleet_expired_fences (
    fence TEXT PRIMARY KEY,
    expired_at_utc TEXT NOT NULL
);
"""

JobStoreStatus = Literal[
    "INTENT",
    "DISPATCHED",
    "RUNNING",
    "ACCEPTED",
    "REJECTED",
    "UNKNOWN_OUTCOME",
    "RECONCILING",
]


def _now() -> datetime:
    return datetime.now(UTC)


class FleetJobStore:
    """Process-restart durable job intents and accepted results."""

    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._connection().executescript(SCHEMA_SQL)

    @classmethod
    def open(cls, root: Path) -> FleetJobStore:
        return cls(root.resolve() / ".local" / "state" / "fleet_jobs" / "jobs.sqlite3")

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
        connection.execute("PRAGMA busy_timeout=30000")
        self._local.db = connection
        return connection

    def persist_intent(self, envelope: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        now = (now or _now()).astimezone(UTC)
        job_id = str(envelope["job_id"])
        if contains_secret_shaped(envelope):
            return {"ok": False, "reason": "secret_in_envelope", "status": "REJECTED"}
        payload = json.dumps(envelope, sort_keys=True, default=str)
        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT status, payload_json FROM fleet_dispatch_intents WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] == payload:
                    db.execute("COMMIT")
                    return {"ok": True, "duplicate": True, "status": existing["status"]}
                if existing["status"] == "INTENT":
                    db.execute(
                        """
                        UPDATE fleet_dispatch_intents SET
                            host_id=?, lease_id=?, fence=?, source_sha=?, source_tree=?,
                            overlay_sha256=?, input_sha256=?, principal=?, profile_id=?,
                            deadline_utc=?, payload_json=?, status='INTENT', created_at_utc=?
                        WHERE job_id=? AND status='INTENT'
                        """,
                        (
                            str(envelope["host_id"]),
                            str(envelope["lease_id"]),
                            str(envelope["fence"]),
                            str(envelope["source_sha"]),
                            str(envelope["source_tree"]),
                            str(envelope["overlay_sha256"]),
                            str(envelope["input_sha256"]),
                            str(envelope["principal"]),
                            str(envelope["profile_id"]),
                            str(envelope["deadline_utc"]),
                            payload,
                            now.isoformat(),
                            job_id,
                        ),
                    )
                    db.execute("COMMIT")
                    return {"ok": True, "duplicate": False, "replaced_unlaunched": True, "status": "INTENT"}
                db.execute("COMMIT")
                return {"ok": False, "reason": "conflicting_intent", "status": existing["status"]}
            db.execute(
                """
                INSERT INTO fleet_dispatch_intents (
                    job_id, host_id, lease_id, fence, source_sha, source_tree,
                    overlay_sha256, input_sha256, principal, profile_id, deadline_utc,
                    payload_json, status, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'INTENT', ?)
                """,
                (
                    job_id,
                    str(envelope["host_id"]),
                    str(envelope["lease_id"]),
                    str(envelope["fence"]),
                    str(envelope["source_sha"]),
                    str(envelope["source_tree"]),
                    str(envelope["overlay_sha256"]),
                    str(envelope["input_sha256"]),
                    str(envelope["principal"]),
                    str(envelope["profile_id"]),
                    str(envelope["deadline_utc"]),
                    payload,
                    now.isoformat(),
                ),
            )
            db.execute("COMMIT")
        return {"ok": True, "duplicate": False, "status": "INTENT"}

    def mark_status(self, job_id: str, status: JobStoreStatus) -> None:
        with self._lock:
            self._connection().execute(
                "UPDATE fleet_dispatch_intents SET status=? WHERE job_id=?",
                (status, job_id),
            )

    def get_intent(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection().execute(
            "SELECT payload_json, status FROM fleet_dispatch_intents WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["status"] = row["status"]
        return payload

    def expire_fence(self, fence: str, *, now: datetime | None = None) -> None:
        now = (now or _now()).astimezone(UTC)
        with self._lock:
            self._connection().execute(
                "INSERT OR REPLACE INTO fleet_expired_fences(fence, expired_at_utc) VALUES (?, ?)",
                (fence, now.isoformat()),
            )

    def fence_expired(self, fence: str) -> bool:
        row = self._connection().execute(
            "SELECT fence FROM fleet_expired_fences WHERE fence=?",
            (fence,),
        ).fetchone()
        return row is not None

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection().execute(
            "SELECT payload_json FROM fleet_job_results WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def accept_result(self, result: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        now = (now or _now()).astimezone(UTC)
        job_id = str(result["job_id"])
        payload = json.dumps(result, sort_keys=True, default=str)
        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT payload_json, output_sha256, exit_code FROM fleet_job_results WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if existing is not None:
                db.execute("COMMIT")
                same = (
                    existing["output_sha256"] == result["output_sha256"]
                    and int(existing["exit_code"]) == int(result["exit_code"])
                )
                if same:
                    return {"outcome": "ACCEPTED", "duplicate": True, "result": json.loads(existing["payload_json"])}
                return {"outcome": "REJECTED", "reason": "conflicting_replay"}
            db.execute(
                """
                INSERT INTO fleet_job_results (
                    job_id, host_id, fence, exit_code, output_sha256, stdout_sha256,
                    stderr_sha256, status, payload_json, accepted_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ACCEPTED', ?, ?)
                """,
                (
                    job_id,
                    str(result["host_id"]),
                    str(result["fence"]),
                    int(result["exit_code"]),
                    str(result["output_sha256"]),
                    str(result["stdout_sha256"]),
                    str(result["stderr_sha256"]),
                    payload,
                    now.isoformat(),
                ),
            )
            db.execute(
                "UPDATE fleet_dispatch_intents SET status='ACCEPTED' WHERE job_id=?",
                (job_id,),
            )
            db.execute("COMMIT")
        return {"outcome": "ACCEPTED", "duplicate": False, "result": result}

    def reconcile_unresolved(self, job_id: str, *, reason: str) -> dict[str, Any]:
        """Allow retry only when no result exists and the prior launch is unresolved."""

        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "SELECT job_id FROM fleet_job_results WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if result is not None:
                db.execute("COMMIT")
                return {"ok": False, "reason": "result_already_accepted"}
            intent = db.execute(
                "SELECT status FROM fleet_dispatch_intents WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if intent is None:
                db.execute("COMMIT")
                return {"ok": True, "reason": "no_intent"}
            if intent["status"] == "ACCEPTED":
                db.execute("COMMIT")
                return {"ok": False, "reason": "already_accepted"}
            db.execute(
                "UPDATE fleet_dispatch_intents SET status='RECONCILING' WHERE job_id=?",
                (job_id,),
            )
            db.execute("DELETE FROM fleet_dispatch_intents WHERE job_id=?", (job_id,))
            db.execute("COMMIT")
        return {"ok": True, "reason": reason, "prior_status": intent["status"]}


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
