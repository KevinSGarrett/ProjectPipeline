from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class LaneLease:
    lane_id: str
    worker_id: str
    fencing_token: str
    expires_at_utc: datetime
    resources: tuple[str, ...]


class LaneRegistry:
    """SQLite-backed conflict-safe lane lease and fencing registry."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init()

    def _init(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lane_leases (
                    lane_id TEXT PRIMARY KEY,
                    worker_id TEXT NOT NULL,
                    fencing_token TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lane_claims (
                    lane_id TEXT NOT NULL,
                    resource_key TEXT NOT NULL,
                    PRIMARY KEY (resource_key),
                    FOREIGN KEY (lane_id) REFERENCES lane_leases(lane_id) ON DELETE CASCADE
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lane_results (
                    lane_id TEXT NOT NULL,
                    fencing_token TEXT NOT NULL,
                    result_fingerprint TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY (lane_id, fencing_token)
                )
                """
            )

    def close(self) -> None:
        self._conn.close()

    def _purge_expired(self, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM lane_leases WHERE expires_at_utc <= ?",
                (_iso(now),),
            )

    @staticmethod
    def _normalize_resources(resources: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({item.strip() for item in resources if item.strip()}))
        if not normalized:
            raise ValueError("lane claim requires at least one non-empty resource key")
        return normalized

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
        now = _utc_now()
        self._purge_expired(now)
        token = str(uuid.uuid4())
        expires_at = now + timedelta(seconds=lease_seconds)
        resources = self._normalize_resources(resources)
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO lane_leases (lane_id, worker_id, fencing_token, expires_at_utc)
                    VALUES (?, ?, ?, ?)
                    """,
                    (lane_id, worker_id, token, _iso(expires_at)),
                )
                for resource in resources:
                    self._conn.execute(
                        "INSERT INTO lane_claims (lane_id, resource_key) VALUES (?, ?)",
                        (lane_id, resource),
                    )
        except sqlite3.IntegrityError:
            return None
        return LaneLease(
            lane_id=lane_id,
            worker_id=worker_id,
            fencing_token=token,
            expires_at_utc=expires_at,
            resources=resources,
        )

    def renew(self, *, lane_id: str, fencing_token: str, lease_seconds: int = 60) -> bool:
        now = _utc_now()
        expires_at = now + timedelta(seconds=lease_seconds)
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE lane_leases
                SET expires_at_utc = ?
                WHERE lane_id = ? AND fencing_token = ? AND expires_at_utc > ?
                """,
                (_iso(expires_at), lane_id, fencing_token, _iso(now)),
            )
        return cursor.rowcount == 1

    def release(self, *, lane_id: str, fencing_token: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM lane_leases WHERE lane_id = ? AND fencing_token = ?",
                (lane_id, fencing_token),
            )
        return cursor.rowcount == 1

    def record_result(self, *, lane_id: str, fencing_token: str, result_fingerprint: str) -> bool:
        now = _utc_now()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            lease_row = self._conn.execute(
                """
                SELECT lane_id FROM lane_leases
                WHERE lane_id = ? AND fencing_token = ? AND expires_at_utc > ?
                """,
                (lane_id, fencing_token, _iso(now)),
            ).fetchone()
            if lease_row is None:
                self._conn.rollback()
                return False
            existing = self._conn.execute(
                """
                SELECT result_fingerprint FROM lane_results
                WHERE lane_id = ? AND fencing_token = ?
                """,
                (lane_id, fencing_token),
            ).fetchone()
            if existing is not None:
                self._conn.rollback()
                return str(existing["result_fingerprint"]) == result_fingerprint
            self._conn.execute(
                """
                INSERT INTO lane_results
                (lane_id, fencing_token, result_fingerprint, created_at_utc)
                VALUES (?, ?, ?, ?)
                """,
                (lane_id, fencing_token, result_fingerprint, _iso(now)),
            )
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise
