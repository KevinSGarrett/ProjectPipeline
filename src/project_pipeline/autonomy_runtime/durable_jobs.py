"""Durable dispatch intents and exactly-once result identity."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
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


def _query_scheduler_lease(
    db: sqlite3.Connection,
    *,
    lease_id: str,
    fence: str,
    now: datetime,
) -> bool | None:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='scheduler_resource_leases'"
    ).fetchone()
    if row is None:
        return None
    lease = db.execute(
        """
        SELECT fencing_token, expires_at_utc, released_at_utc
        FROM scheduler_resource_leases
        WHERE lease_id=?
        """,
        (lease_id,),
    ).fetchone()
    if lease is None:
        return False
    if lease["released_at_utc"]:
        return False
    expires = datetime.fromisoformat(str(lease["expires_at_utc"]).replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if now > expires.astimezone(UTC):
        return False
    return not fence or str(lease["fencing_token"]) == str(fence)


def _scheduler_lease_active(
    db: sqlite3.Connection,
    *,
    lease_id: str,
    fence: str,
    now: datetime,
    scheduler_database: Path | None = None,
) -> bool:
    found = _query_scheduler_lease(db, lease_id=lease_id, fence=fence, now=now)
    if found is not None:
        return found
    if scheduler_database is None:
        return False
    extra = sqlite3.connect(str(scheduler_database))
    extra.row_factory = sqlite3.Row
    try:
        found = _query_scheduler_lease(extra, lease_id=lease_id, fence=fence, now=now)
        return bool(found)
    finally:
        extra.close()


class FleetJobStore:
    """Process-restart durable job intents and accepted results."""

    def __init__(self, database: Path, scheduler_database: Path | None = None) -> None:
        self.database = Path(database)
        self.scheduler_database = Path(scheduler_database) if scheduler_database else None
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

    def persist_intent(
        self, envelope: dict[str, Any], *, now: datetime | None = None
    ) -> dict[str, Any]:
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
                    return {
                        "ok": True,
                        "duplicate": False,
                        "replaced_unlaunched": True,
                        "status": "INTENT",
                    }
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

    def release_unlaunched(self, job_id: str) -> None:
        """Return DISPATCHED to INTENT when no remote process was started."""

        with self._lock:
            self._connection().execute(
                """
                UPDATE fleet_dispatch_intents SET status='INTENT'
                WHERE job_id=? AND status='DISPATCHED'
                """,
                (job_id,),
            )

    def get_intent(self, job_id: str) -> dict[str, Any] | None:
        row = (
            self._connection()
            .execute(
                "SELECT payload_json, status FROM fleet_dispatch_intents WHERE job_id=?",
                (job_id,),
            )
            .fetchone()
        )
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["status"] = row["status"]
        return payload

    def remember_scheduler_lease(
        self,
        lease_id: str,
        fence: str,
        *,
        now: datetime | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        now = (now or _now()).astimezone(UTC)
        expires = now + timedelta(seconds=ttl_seconds)
        with self._lock:
            db = self._connection()
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_resource_leases (
                    lease_id TEXT PRIMARY KEY,
                    fencing_token TEXT,
                    expires_at_utc TEXT NOT NULL,
                    released_at_utc TEXT
                )
                """
            )
            db.execute(
                """
                INSERT OR REPLACE INTO scheduler_resource_leases
                    (lease_id, fencing_token, expires_at_utc, released_at_utc)
                VALUES (?, ?, ?, NULL)
                """,
                (lease_id, fence, expires.isoformat()),
            )

    def expire_fence(self, fence: str, *, now: datetime | None = None) -> None:
        now = (now or _now()).astimezone(UTC)
        with self._lock:
            self._connection().execute(
                "INSERT OR REPLACE INTO fleet_expired_fences(fence, expired_at_utc) VALUES (?, ?)",
                (fence, now.isoformat()),
            )

    def fence_expired(self, fence: str) -> bool:
        row = (
            self._connection()
            .execute(
                "SELECT fence FROM fleet_expired_fences WHERE fence=?",
                (fence,),
            )
            .fetchone()
        )
        return row is not None

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        row = (
            self._connection()
            .execute(
                "SELECT payload_json FROM fleet_job_results WHERE job_id=?",
                (job_id,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def accept_result(
        self,
        result: dict[str, Any],
        *,
        now: datetime | None = None,
        envelope: dict[str, Any] | None = None,
        artifact_bytes: bytes | None = None,
        context_consumption: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = (now or _now()).astimezone(UTC)
        job_id = str(result.get("job_id") or "")
        if not job_id:
            return {"outcome": "REJECTED", "reason": "job_id_missing"}
        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            intent_row = db.execute(
                "SELECT payload_json, status FROM fleet_dispatch_intents WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if intent_row is None:
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "intent_missing"}
            stored = json.loads(intent_row["payload_json"])
            stored.pop("status", None)
            expected = dict(envelope or {})
            expected.pop("status", None)
            if expected and stored != expected:
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "conflicting_intent"}
            if str(result.get("host_id") or "") != str(stored.get("host_id") or ""):
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "wrong_host"}
            if str(result.get("fence") or "") != str(stored.get("fence") or ""):
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "expired_fence"}
            expired = db.execute(
                "SELECT fence FROM fleet_expired_fences WHERE fence=?",
                (str(stored.get("fence") or ""),),
            ).fetchone()
            if expired is not None:
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "expired_fence"}
            deadline = datetime.fromisoformat(
                str(stored.get("deadline_utc") or "").replace("Z", "+00:00")
            ).astimezone(UTC)
            if now > deadline:
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "late_result"}
            try:
                exit_code = int(result.get("exit_code"))
            except (TypeError, ValueError):
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "nonzero_exit"}
            if exit_code != 0:
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "nonzero_exit"}
            contract = str(stored.get("output_contract_sha256") or "")
            require_bytes = bool(contract) or bool(stored.get("require_context_consumption"))
            if require_bytes:
                if artifact_bytes is None:
                    db.execute("COMMIT")
                    return {"outcome": "REJECTED", "reason": "artifact_bytes_required"}
                actual_output = digest_bytes(artifact_bytes)
                claimed = str(result.get("artifact_sha256") or result.get("junit_sha256") or "")
                expected_output = contract or claimed
                if expected_output and actual_output != expected_output:
                    db.execute("COMMIT")
                    return {"outcome": "REJECTED", "reason": "output_tamper"}
                result = dict(result)
                result["artifact_sha256"] = actual_output
                if not contract:
                    result["output_sha256"] = actual_output
            if stored.get("require_context_consumption"):
                receipt = context_consumption if isinstance(context_consumption, dict) else {}
                if not receipt.get("ok"):
                    db.execute("COMMIT")
                    return {"outcome": "REJECTED", "reason": "context_unconsumed"}
                if str(receipt.get("job_id") or "") != str(stored.get("job_id") or ""):
                    db.execute("COMMIT")
                    return {"outcome": "REJECTED", "reason": "context_wrong_job"}
                if str(receipt.get("host_id") or "") != str(stored.get("host_id") or ""):
                    db.execute("COMMIT")
                    return {"outcome": "REJECTED", "reason": "context_wrong_host"}
                expected_pack = str(stored.get("pack_sha256") or "")
                if expected_pack and str(receipt.get("pack_sha256") or "") != expected_pack:
                    db.execute("COMMIT")
                    return {"outcome": "REJECTED", "reason": "context_wrong_pack"}
            lease_id = str(stored.get("lease_id") or "")
            if lease_id and not _scheduler_lease_active(
                db,
                lease_id=lease_id,
                fence=str(stored.get("fence") or ""),
                now=now,
                scheduler_database=self.scheduler_database,
            ):
                db.execute("COMMIT")
                return {"outcome": "REJECTED", "reason": "scheduler_lease_inactive"}
            existing = db.execute(
                "SELECT payload_json, output_sha256, exit_code FROM fleet_job_results WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if existing is not None:
                db.execute("COMMIT")
                same = existing["output_sha256"] == result["output_sha256"] and int(
                    existing["exit_code"]
                ) == int(result["exit_code"])
                if same:
                    return {
                        "outcome": "ACCEPTED",
                        "duplicate": True,
                        "result": json.loads(existing["payload_json"]),
                    }
                return {"outcome": "REJECTED", "reason": "conflicting_replay"}
            payload = json.dumps(result, sort_keys=True, default=str)
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

    def claim_launch(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Atomically take INTENT -> DISPATCHED for one matching payload."""

        job_id = str(envelope["job_id"])
        payload = json.dumps(envelope, sort_keys=True, default=str)
        with self._lock:
            db = self._connection()
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT status, payload_json FROM fleet_dispatch_intents WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if existing is None:
                db.execute("COMMIT")
                return {"ok": False, "reason": "intent_missing"}
            stored = json.loads(existing["payload_json"])
            stored.pop("status", None)
            incoming = json.loads(payload)
            incoming.pop("status", None)
            if stored != incoming:
                db.execute("COMMIT")
                return {"ok": False, "reason": "conflicting_intent"}
            if existing["status"] in {"DISPATCHED", "RUNNING", "UNKNOWN_OUTCOME", "RECONCILING"}:
                db.execute("COMMIT")
                return {"ok": False, "reason": "unresolved_in_flight", "status": existing["status"]}
            if existing["status"] == "ACCEPTED":
                db.execute("COMMIT")
                return {"ok": False, "reason": "already_accepted"}
            updated = db.execute(
                """
                UPDATE fleet_dispatch_intents SET status='DISPATCHED'
                WHERE job_id=? AND status='INTENT'
                """,
                (job_id,),
            )
            db.execute("COMMIT")
            if updated.rowcount != 1:
                return {"ok": False, "reason": "unresolved_in_flight"}
            return {"ok": True, "status": "DISPATCHED"}

    def reconcile_unresolved(
        self,
        job_id: str,
        *,
        reason: str,
        absence_proof: bool = False,
    ) -> dict[str, Any]:
        """Keep RUNNING/UNKNOWN occupancy until absence is proven."""

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
            if (
                intent["status"] in {"RUNNING", "DISPATCHED", "UNKNOWN_OUTCOME"}
                and not absence_proof
            ):
                db.execute("COMMIT")
                return {
                    "ok": False,
                    "reason": "absence_proof_required",
                    "prior_status": intent["status"],
                }
            db.execute(
                "UPDATE fleet_dispatch_intents SET status='RECONCILING' WHERE job_id=?",
                (job_id,),
            )
            db.execute("COMMIT")
        return {"ok": True, "reason": reason, "prior_status": intent["status"]}


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
