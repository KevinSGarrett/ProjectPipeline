from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

STAGES = ("RECOVERY", "UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR")
H24 = timedelta(hours=24)
H72 = timedelta(hours=72)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class QualificationStore:
    """Durable unattended-qualification checkpoints. Elapsed time is attested, never assigned."""

    def __init__(self, path: Path, *, clock: Clock | None = None) -> None:
        self.path = path
        self.clock = clock or SystemClock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS qualification_runs (
                    run_id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    process_id INTEGER NOT NULL,
                    state_path TEXT NOT NULL,
                    started_at_utc TEXT NOT NULL,
                    last_heartbeat_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attested_elapsed_seconds REAL NOT NULL,
                    fence TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    prior_run_id TEXT
                );
                CREATE TABLE IF NOT EXISTS qualification_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        self._db.close()

    def start(
        self,
        stage: str,
        *,
        state_path: Path,
        process_id: int | None = None,
        prior_run_id: str | None = None,
    ) -> dict[str, Any]:
        if stage not in STAGES:
            raise ValueError(f"unsupported qualification stage: {stage}")
        if stage == "UNATTENDED_72_HOUR" and not self._twenty_four_hour_attested():
            raise ValueError("72-hour admission requires a prior attested 24-hour run")
        now = self._attestation_now(stage)
        payload = {
            "stage": stage,
            "started_at_utc": now.isoformat(),
            "state_path": str(state_path),
        }
        run_id = (
            "QRUN-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        )
        fence = "QFENCE-" + hashlib.sha256(run_id.encode()).hexdigest()[:12]
        lease_id = "QLEASE-" + hashlib.sha256((run_id + fence).encode()).hexdigest()[:12]
        with self._db:
            self._db.execute(
                """
                INSERT INTO qualification_runs (
                    run_id, stage, process_id, state_path, started_at_utc, last_heartbeat_utc,
                    status, attested_elapsed_seconds, fence, lease_id, prior_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', 0, ?, ?, ?)
                """,
                (
                    run_id,
                    stage,
                    int(process_id if process_id is not None else os.getpid()),
                    str(state_path),
                    now.isoformat(),
                    now.isoformat(),
                    fence,
                    lease_id,
                    prior_run_id,
                ),
            )
            self._audit(run_id, "START", "RUNNING", now)
        return self.get(run_id)

    def _attestation_now(self, stage: str) -> datetime:
        if stage in {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"}:
            return datetime.now(UTC)
        return self.clock.now()

    def heartbeat(self, run_id: str) -> dict[str, Any]:
        row = self._require(run_id)
        if str(row["status"]) not in {"RUNNING", "RESUMED"}:
            raise ValueError("heartbeat denied unless the run is active")
        now = self._attestation_now(str(row["stage"]))
        elapsed = self._elapsed_seconds(row, now)
        with self._db:
            self._db.execute(
                """
                UPDATE qualification_runs
                SET last_heartbeat_utc = ?, attested_elapsed_seconds = ?, status = 'RUNNING'
                WHERE run_id = ?
                """,
                (now.isoformat(), elapsed, run_id),
            )
            self._audit(run_id, "HEARTBEAT", "RUNNING", now)
        return self.get(run_id)

    def resume(self, run_id: str, *, process_id: int | None = None) -> dict[str, Any]:
        row = self._require(run_id)
        if str(row["status"]) not in {"RUNNING", "RESUMED", "FAILED"}:
            raise ValueError("only an interrupted or failed run can resume")
        now = self._attestation_now(str(row["stage"]))
        elapsed = self._elapsed_seconds(row, now)
        with self._db:
            self._db.execute(
                """
                UPDATE qualification_runs
                SET process_id = ?, last_heartbeat_utc = ?, attested_elapsed_seconds = ?, status = 'RESUMED'
                WHERE run_id = ?
                """,
                (
                    int(process_id if process_id is not None else os.getpid()),
                    now.isoformat(),
                    elapsed,
                    run_id,
                ),
            )
            self._audit(run_id, "RESUME", "RESUMED", now)
        return self.get(run_id)

    def fail(self, run_id: str, *, reason: str) -> dict[str, Any]:
        row = self._require(run_id)
        now = self._attestation_now(str(row["stage"]))
        elapsed = self._elapsed_seconds(row, now)
        with self._db:
            self._db.execute(
                """
                UPDATE qualification_runs
                SET status = 'FAILED', attested_elapsed_seconds = ?, last_heartbeat_utc = ?
                WHERE run_id = ?
                """,
                (elapsed, now.isoformat(), run_id),
            )
            self._audit(run_id, f"FAIL:{reason}", "FAILED", now)
        return self.get(run_id)

    def complete(self, run_id: str) -> dict[str, Any]:
        row = self._require(run_id)
        stage = str(row["stage"])
        now = self._attestation_now(stage)
        elapsed = self._elapsed_seconds(row, now)
        required = H24 if stage == "UNATTENDED_24_HOUR" else H72
        if (
            stage in {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"}
            and elapsed < required.total_seconds()
        ):
            raise ValueError("elapsed time cannot be simulated or shortened")
        if str(row["stage"]) == "UNATTENDED_72_HOUR" and not self._twenty_four_hour_attested():
            raise ValueError("72-hour completion requires attested 24-hour admission")
        with self._db:
            self._db.execute(
                """
                UPDATE qualification_runs
                SET status = 'ATTESTED', attested_elapsed_seconds = ?, last_heartbeat_utc = ?
                WHERE run_id = ?
                """,
                (elapsed, now.isoformat(), run_id),
            )
            self._audit(run_id, "ATTEST", "ATTESTED", now)
        return self.get(run_id)

    def health(self, run_id: str) -> dict[str, Any]:
        row = self.get(run_id)
        now = self._attestation_now(str(row["stage"]))
        return {
            **row,
            "elapsed_seconds": self._elapsed_seconds(self._require(run_id), now),
            "stop_command": [
                "python",
                "scripts/run_autonomy_qualification.py",
                "fail",
                "--run-id",
                run_id,
            ],
            "resume_command": [
                "python",
                "scripts/run_autonomy_qualification.py",
                "resume",
                "--run-id",
                run_id,
            ],
            "simulated_elapsed": False,
        }

    def get(self, run_id: str) -> dict[str, Any]:
        return dict(self._require(run_id))

    def _twenty_four_hour_attested(self) -> bool:
        row = self._db.execute(
            """
            SELECT attested_elapsed_seconds FROM qualification_runs
            WHERE stage = 'UNATTENDED_24_HOUR' AND status = 'ATTESTED'
            ORDER BY started_at_utc DESC LIMIT 1
            """
        ).fetchone()
        return row is not None and float(row["attested_elapsed_seconds"]) >= H24.total_seconds()

    def _elapsed_seconds(self, row: sqlite3.Row, now: datetime) -> float:
        started = datetime.fromisoformat(str(row["started_at_utc"]))
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return max(0.0, (now - started).total_seconds())

    def _require(self, run_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM qualification_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown qualification run: {run_id}")
        return cast(sqlite3.Row, row)

    def _audit(self, run_id: str, action: str, status: str, now: datetime) -> None:
        self._db.execute(
            """
            INSERT INTO qualification_audit (run_id, action, status, created_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, action, status, now.isoformat()),
        )
