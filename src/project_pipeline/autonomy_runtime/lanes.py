from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
DEFAULT_MAX_ATTEMPTS = 3
Clock = Callable[[], datetime]


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonicalize_resource(resource: str) -> str:
    item = resource.strip()
    if not item:
        raise ValueError("resource key must be non-empty")
    prefix, separator, remainder = item.partition(":")
    if separator and prefix.upper() == "PATH":
        normalized = os.path.normpath(remainder).replace("/", "\\").casefold()
        while "\\\\" in normalized:
            normalized = normalized.replace("\\\\", "\\")
        if not normalized or normalized in {".", "\\"}:
            raise ValueError("PATH resource must not resolve to an empty or root path")
        return f"PATH:{normalized}"
    return item


def canonicalize_resources(resources: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(canonicalize_resource(item) for item in resources if item.strip())
    if not normalized:
        raise ValueError("lane claim requires at least one non-empty resource key")
    if len(set(normalized)) != len(normalized):
        raise ValueError("lane claim contains duplicate or conflicting resource keys")
    return tuple(sorted(set(normalized)))


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LaneLease:
    lane_id: str
    worker_id: str
    fencing_token: str
    expires_at_utc: datetime
    resources: tuple[str, ...]
    attempt_id: str
    attempt_number: int


@dataclass(frozen=True)
class LaneIncident:
    incident_id: str
    logical_lane_id: str
    attempt_id: str | None
    reason: str
    disposition: str
    failure_fingerprint: str
    retry_decision: str | None
    created_at_utc: datetime


class LaneRegistry:
    """Durable conflict-safe lane lease, attempt, and fencing registry."""

    def __init__(
        self,
        db_path: Path,
        *,
        clock: Clock | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: datetime.now(UTC))
        self.max_attempts = max_attempts
        self._conn = sqlite3.connect(str(db_path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        self._init()

    def _configure_connection(self) -> None:
        last_error: sqlite3.OperationalError | None = None
        for _ in range(10):
            try:
                self._conn.execute("PRAGMA busy_timeout = 30000")
                self._conn.execute("PRAGMA journal_mode = WAL")
                self._conn.execute("PRAGMA foreign_keys = ON")
                return
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                last_error = exc
                time.sleep(0.05)
        if last_error is not None:
            raise last_error

    def close(self) -> None:
        self._conn.close()

    def _now(self) -> datetime:
        return self._clock()

    def _meta_get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value_json FROM lane_schema_meta WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return default
        return json.loads(str(row["value_json"]))

    def _meta_put_conn(self, key: str, value: Any) -> None:
        self._conn.execute(
            """
            INSERT INTO lane_schema_meta (key, value_json)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
            """,
            (key, json.dumps(value, sort_keys=True)),
        )

    def _init(self) -> None:
        self._conn.isolation_level = None
        last_error: sqlite3.OperationalError | None = None
        for _ in range(10):
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                last_error = exc
                time.sleep(0.05)
        else:
            if last_error is not None:
                raise last_error
        try:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lane_schema_meta (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                )
                """
            )
            version = int(self._meta_get("schema_version", 0))
            if version == 0:
                self._create_v2_schema()
                self._meta_put_conn("schema_version", SCHEMA_VERSION)
            elif version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported lane registry schema {version}; expected {SCHEMA_VERSION}"
                )
            present = {
                str(row["name"])
                for row in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            required = {
                "lane_attempts",
                "lane_leases",
                "lane_claims",
                "lane_results",
                "lane_heartbeats",
                "lane_incidents",
            }
            missing = sorted(required - present)
            if missing:
                raise RuntimeError(
                    "lane registry schema is missing tables "
                    f"{missing}; refuse ad hoc create that would mask a failed migration"
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self._conn.isolation_level = "DEFERRED"

    def _create_v2_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lane_attempts (
                attempt_id TEXT PRIMARY KEY,
                logical_lane_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                fencing_token TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL,
                resources_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                expires_at_utc TEXT NOT NULL,
                fenced_at_utc TEXT,
                UNIQUE (logical_lane_id, attempt_number)
            );
            CREATE TABLE IF NOT EXISTS lane_leases (
                logical_lane_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL UNIQUE,
                worker_id TEXT NOT NULL,
                fencing_token TEXT NOT NULL UNIQUE,
                expires_at_utc TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES lane_attempts(attempt_id)
            );
            CREATE TABLE IF NOT EXISTS lane_claims (
                resource_key TEXT PRIMARY KEY,
                logical_lane_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES lane_attempts(attempt_id)
            );
            CREATE TABLE IF NOT EXISTS lane_results (
                attempt_id TEXT PRIMARY KEY,
                logical_lane_id TEXT NOT NULL,
                fencing_token TEXT NOT NULL,
                result_fingerprint TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES lane_attempts(attempt_id)
            );
            CREATE TABLE IF NOT EXISTS lane_heartbeats (
                heartbeat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id TEXT NOT NULL,
                logical_lane_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                fencing_token TEXT NOT NULL,
                intent_json TEXT NOT NULL,
                recorded_at_utc TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES lane_attempts(attempt_id)
            );
            CREATE TABLE IF NOT EXISTS lane_incidents (
                incident_id TEXT PRIMARY KEY,
                logical_lane_id TEXT NOT NULL,
                attempt_id TEXT,
                reason TEXT NOT NULL,
                disposition TEXT NOT NULL,
                failure_fingerprint TEXT NOT NULL,
                retry_decision TEXT,
                created_at_utc TEXT NOT NULL
            );
            """
        )

    def _active_lease(self, lane_id: str) -> sqlite3.Row | None:
        row = self._conn.execute(
            "SELECT * FROM lane_leases WHERE logical_lane_id = ?",
            (lane_id,),
        ).fetchone()
        if row is None:
            return None
        if not isinstance(row, sqlite3.Row):
            raise TypeError("expected sqlite3.Row lease record")
        return row

    def _attempt_count(self, lane_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM lane_attempts WHERE logical_lane_id = ?",
            (lane_id,),
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    def _record_incident_conn(
        self,
        *,
        logical_lane_id: str,
        attempt_id: str | None,
        reason: str,
        disposition: str,
        retry_decision: str | None,
    ) -> LaneIncident:
        now = self._now()
        payload = {
            "logical_lane_id": logical_lane_id,
            "attempt_id": attempt_id,
            "reason": reason,
            "disposition": disposition,
            "retry_decision": retry_decision,
            "created_at_utc": _iso(now),
        }
        incident = LaneIncident(
            incident_id=f"INC-{uuid.uuid4()}",
            logical_lane_id=logical_lane_id,
            attempt_id=attempt_id,
            reason=reason,
            disposition=disposition,
            failure_fingerprint=_digest(payload),
            retry_decision=retry_decision,
            created_at_utc=now,
        )
        self._conn.execute(
            """
            INSERT INTO lane_incidents (
                incident_id, logical_lane_id, attempt_id, reason, disposition,
                failure_fingerprint, retry_decision, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident.incident_id,
                incident.logical_lane_id,
                incident.attempt_id,
                incident.reason,
                incident.disposition,
                incident.failure_fingerprint,
                incident.retry_decision,
                _iso(incident.created_at_utc),
            ),
        )
        return incident

    def _fence_attempt_conn(
        self,
        *,
        attempt_id: str,
        logical_lane_id: str,
        reason: str,
        disposition: str,
        retry_decision: str | None,
    ) -> LaneIncident:
        now = self._now()
        self._conn.execute(
            """
            UPDATE lane_attempts
            SET state = ?, fenced_at_utc = ?
            WHERE attempt_id = ? AND state = 'ACTIVE'
            """,
            ("FENCED", _iso(now), attempt_id),
        )
        self._conn.execute(
            "DELETE FROM lane_leases WHERE logical_lane_id = ?",
            (logical_lane_id,),
        )
        self._conn.execute(
            "DELETE FROM lane_claims WHERE attempt_id = ?",
            (attempt_id,),
        )
        return self._record_incident_conn(
            logical_lane_id=logical_lane_id,
            attempt_id=attempt_id,
            reason=reason,
            disposition=disposition,
            retry_decision=retry_decision,
        )

    def _expire_due_leases_conn(self, now: datetime) -> None:
        rows = self._conn.execute(
            "SELECT * FROM lane_leases WHERE expires_at_utc <= ?",
            (_iso(now),),
        ).fetchall()
        for row in rows:
            self._fence_attempt_conn(
                attempt_id=str(row["attempt_id"]),
                logical_lane_id=str(row["logical_lane_id"]),
                reason="LEASE_EXPIRED",
                disposition="RECOVERED",
                retry_decision="ALLOW_REPLACEMENT",
            )

    def _authorized_lease(
        self,
        *,
        lane_id: str,
        worker_id: str,
        fencing_token: str,
        now: datetime,
    ) -> sqlite3.Row | None:
        row = self._conn.execute(
            """
            SELECT * FROM lane_leases
            WHERE logical_lane_id = ?
              AND worker_id = ?
              AND fencing_token = ?
              AND expires_at_utc > ?
            """,
            (lane_id, worker_id, fencing_token, _iso(now)),
        ).fetchone()
        if row is None:
            return None
        if not isinstance(row, sqlite3.Row):
            raise TypeError("expected sqlite3.Row authorized lease")
        return row

    def claim(
        self,
        *,
        lane_id: str,
        worker_id: str,
        resources: tuple[str, ...],
        lease_seconds: int = 60,
    ) -> LaneLease | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        resources = canonicalize_resources(resources)
        now = self._now()
        try:
            with self._conn:
                self._expire_due_leases_conn(now)
                if self._active_lease(lane_id) is not None:
                    return None
                attempt_number = self._attempt_count(lane_id) + 1
                if attempt_number > self.max_attempts:
                    self._record_incident_conn(
                        logical_lane_id=lane_id,
                        attempt_id=None,
                        reason="RETRY_EXHAUSTED",
                        disposition="HUMAN_REQUIRED",
                        retry_decision="DENY",
                    )
                    return None
                attempt_id = f"ATT-{uuid.uuid4()}"
                token = str(uuid.uuid4())
                expires_at = now + timedelta(seconds=lease_seconds)
                self._conn.execute(
                    """
                    INSERT INTO lane_attempts (
                        attempt_id, logical_lane_id, attempt_number, worker_id,
                        fencing_token, state, resources_json, created_at_utc, expires_at_utc
                    ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                    """,
                    (
                        attempt_id,
                        lane_id,
                        attempt_number,
                        worker_id,
                        token,
                        json.dumps(list(resources), sort_keys=True),
                        _iso(now),
                        _iso(expires_at),
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO lane_leases (
                        logical_lane_id, attempt_id, worker_id, fencing_token, expires_at_utc
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (lane_id, attempt_id, worker_id, token, _iso(expires_at)),
                )
                for resource in resources:
                    self._conn.execute(
                        """
                        INSERT INTO lane_claims (resource_key, logical_lane_id, attempt_id)
                        VALUES (?, ?, ?)
                        """,
                        (resource, lane_id, attempt_id),
                    )
        except sqlite3.IntegrityError:
            return None
        return LaneLease(
            lane_id=lane_id,
            worker_id=worker_id,
            fencing_token=token,
            expires_at_utc=expires_at,
            resources=resources,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
        )

    def renew(
        self,
        *,
        lane_id: str,
        worker_id: str,
        fencing_token: str,
        lease_seconds: int = 60,
    ) -> bool:
        now = self._now()
        expires_at = now + timedelta(seconds=lease_seconds)
        with self._conn:
            self._expire_due_leases_conn(now)
            cursor = self._conn.execute(
                """
                UPDATE lane_leases
                SET expires_at_utc = ?
                WHERE logical_lane_id = ?
                  AND worker_id = ?
                  AND fencing_token = ?
                  AND expires_at_utc > ?
                """,
                (_iso(expires_at), lane_id, worker_id, fencing_token, _iso(now)),
            )
            if cursor.rowcount != 1:
                return False
            self._conn.execute(
                """
                UPDATE lane_attempts
                SET expires_at_utc = ?
                WHERE fencing_token = ? AND state = 'ACTIVE'
                """,
                (_iso(expires_at), fencing_token),
            )
        return True

    def release(self, *, lane_id: str, worker_id: str, fencing_token: str) -> bool:
        now = self._now()
        with self._conn:
            self._expire_due_leases_conn(now)
            lease = self._authorized_lease(
                lane_id=lane_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
                now=now,
            )
            if lease is None:
                return False
            self._fence_attempt_conn(
                attempt_id=str(lease["attempt_id"]),
                logical_lane_id=lane_id,
                reason="LEASE_RELEASED",
                disposition="RECOVERED",
                retry_decision="ALLOW_REPLACEMENT",
            )
        return True

    def heartbeat(
        self,
        *,
        lane_id: str,
        worker_id: str,
        fencing_token: str,
        intent: dict[str, Any] | None = None,
    ) -> bool:
        now = self._now()
        with self._conn:
            self._expire_due_leases_conn(now)
            lease = self._authorized_lease(
                lane_id=lane_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
                now=now,
            )
            if lease is None:
                return False
            self._conn.execute(
                """
                INSERT INTO lane_heartbeats (
                    attempt_id, logical_lane_id, worker_id, fencing_token,
                    intent_json, recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(lease["attempt_id"]),
                    lane_id,
                    worker_id,
                    fencing_token,
                    json.dumps(intent or {}, sort_keys=True),
                    _iso(now),
                ),
            )
        return True

    def record_result(
        self,
        *,
        lane_id: str,
        fencing_token: str,
        result_fingerprint: str,
        worker_id: str | None = None,
    ) -> bool:
        now = self._now()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._expire_due_leases_conn(now)
            if worker_id is None:
                lease_row = self._conn.execute(
                    """
                    SELECT * FROM lane_leases
                    WHERE logical_lane_id = ? AND fencing_token = ? AND expires_at_utc > ?
                    """,
                    (lane_id, fencing_token, _iso(now)),
                ).fetchone()
            else:
                lease_row = self._authorized_lease(
                    lane_id=lane_id,
                    worker_id=worker_id,
                    fencing_token=fencing_token,
                    now=now,
                )
            if lease_row is None:
                self._conn.rollback()
                return False
            attempt_id = str(lease_row["attempt_id"])
            existing = self._conn.execute(
                "SELECT result_fingerprint FROM lane_results WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if existing is not None:
                self._conn.rollback()
                return str(existing["result_fingerprint"]) == result_fingerprint
            self._conn.execute(
                """
                INSERT INTO lane_results
                    (attempt_id, logical_lane_id, fencing_token, result_fingerprint, created_at_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (attempt_id, lane_id, fencing_token, result_fingerprint, _iso(now)),
            )
            self._conn.execute(
                "UPDATE lane_attempts SET state = 'COMPLETED' WHERE attempt_id = ?",
                (attempt_id,),
            )
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def recover_lost_worker(
        self,
        *,
        lane_id: str,
        stale_fencing_token: str,
        stale_worker_id: str | None = None,
    ) -> LaneIncident:
        now = self._now()
        with self._conn:
            self._expire_due_leases_conn(now)
            lease = self._active_lease(lane_id)
            if lease is None:
                latest = self._conn.execute(
                    """
                    SELECT * FROM lane_attempts
                    WHERE logical_lane_id = ?
                    ORDER BY attempt_number DESC
                    LIMIT 1
                    """,
                    (lane_id,),
                ).fetchone()
                if latest is not None and str(latest["state"]) == "HUMAN_REQUIRED":
                    return LaneIncident(
                        incident_id="existing",
                        logical_lane_id=lane_id,
                        attempt_id=str(latest["attempt_id"]),
                        reason="ALREADY_HUMAN_REQUIRED",
                        disposition="HUMAN_REQUIRED",
                        failure_fingerprint=str(latest["attempt_id"]),
                        retry_decision="DENY",
                        created_at_utc=now,
                    )
                return self._record_incident_conn(
                    logical_lane_id=lane_id,
                    attempt_id=None if latest is None else str(latest["attempt_id"]),
                    reason="UNRESOLVED_STALE_OR_UNKNOWN_LEASE",
                    disposition="HUMAN_REQUIRED",
                    retry_decision="DENY",
                )
            token_matches = str(lease["fencing_token"]) == stale_fencing_token
            owner_matches = stale_worker_id is None or str(lease["worker_id"]) == stale_worker_id
            if token_matches and owner_matches:
                return self._fence_attempt_conn(
                    attempt_id=str(lease["attempt_id"]),
                    logical_lane_id=lane_id,
                    reason="WORKER_LOSS",
                    disposition="RECOVERED",
                    retry_decision="ALLOW_REPLACEMENT",
                )
            return self._record_incident_conn(
                logical_lane_id=lane_id,
                attempt_id=str(lease["attempt_id"]),
                reason="UNSOLVABLE_LIVE_LEASE_WITHOUT_MATCHING_FENCE",
                disposition="HUMAN_REQUIRED",
                retry_decision="DENY",
            )

    def list_incidents(self, lane_id: str | None = None) -> list[LaneIncident]:
        if lane_id is None:
            rows = self._conn.execute(
                "SELECT * FROM lane_incidents ORDER BY created_at_utc, rowid"
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM lane_incidents
                WHERE logical_lane_id = ?
                ORDER BY created_at_utc, rowid
                """,
                (lane_id,),
            ).fetchall()
        return [
            LaneIncident(
                incident_id=str(row["incident_id"]),
                logical_lane_id=str(row["logical_lane_id"]),
                attempt_id=None if row["attempt_id"] is None else str(row["attempt_id"]),
                reason=str(row["reason"]),
                disposition=str(row["disposition"]),
                failure_fingerprint=str(row["failure_fingerprint"]),
                retry_decision=None
                if row["retry_decision"] is None
                else str(row["retry_decision"]),
                created_at_utc=_from_iso(str(row["created_at_utc"])),
            )
            for row in rows
        ]

    def list_attempts(self, lane_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM lane_attempts
            WHERE logical_lane_id = ?
            ORDER BY attempt_number
            """,
            (lane_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def result_for_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM lane_results WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def heartbeats_for_attempt(self, attempt_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM lane_heartbeats
            WHERE attempt_id = ?
            ORDER BY heartbeat_id
            """,
            (attempt_id,),
        ).fetchall()
        return [dict(row) for row in rows]
