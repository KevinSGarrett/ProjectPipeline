from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from project_pipeline.persistence.migrations import SQLiteMigrationRunner

STAGES = ("RECOVERY", "UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR")
H24 = timedelta(hours=24)
H72 = timedelta(hours=72)
REQUIRED_TABLES = ("qualification_runs", "qualification_events", "qualification_locks")
ACTIVE = {"RUNNING", "RESUMED"}


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _default_repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "database" / "MIGRATION_CATALOG.json").is_file():
            return parent
    raise RuntimeError("repository root with migration catalog was not found")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _windows_pid_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return int(exit_code.value) == still_active
    finally:
        kernel32.CloseHandle(handle)


class QualificationStore:
    """Catalog-migrated unattended qualification runner. Elapsed time is attested, never assigned."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Clock | None = None,
        repository_root: Path | None = None,
        heartbeat_seconds: float = 30.0,
    ) -> None:
        self.path = path
        self.clock = clock or SystemClock()
        self.heartbeat_seconds = float(heartbeat_seconds)
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat cadence must be positive")
        self.repository_root = (
            repository_root.resolve() if repository_root is not None else _default_repository_root()
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        SQLiteMigrationRunner(self._db, self.repository_root).apply_all()
        present = {
            str(row["name"])
            for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = [name for name in REQUIRED_TABLES if name not in present]
        if missing:
            raise RuntimeError(
                "qualification schema is missing catalog tables "
                f"{missing}; apply PPDB-0021 rather than creating tables ad hoc"
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
        self._reject_concurrent_lock()
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
        lock_token = (
            "QLOCK-" + hashlib.sha256((run_id + str(os.getpid())).encode()).hexdigest()[:12]
        )
        pid = int(process_id if process_id is not None else os.getpid())
        with self._db:
            self._db.execute(
                """
                INSERT INTO qualification_runs (
                    run_id, stage, process_id, state_path, started_at_utc, last_heartbeat_utc,
                    status, attested_elapsed_seconds, fence, lease_id, prior_run_id,
                    window_broken, last_event_sha256, heartbeat_cadence_seconds, lock_token
                ) VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', 0, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    run_id,
                    stage,
                    pid,
                    str(state_path),
                    now.isoformat(),
                    now.isoformat(),
                    fence,
                    lease_id,
                    prior_run_id,
                    self.heartbeat_seconds,
                    lock_token,
                ),
            )
            self._db.execute(
                """
                INSERT INTO qualification_locks (lock_name, run_id, process_id, fence, acquired_at_utc)
                VALUES ('active-qualification', ?, ?, ?, ?)
                """,
                (run_id, pid, fence, now.isoformat()),
            )
            self._append_event(run_id, "START", "RUNNING", {"stage": stage}, now)
        return self.get(run_id)

    def recovery_drill(self, *, state_path: Path) -> dict[str, Any]:
        started = self.start("RECOVERY", state_path=state_path)
        failed = self.fail(started["run_id"], reason="controlled-process-loss")
        resumed = self.resume(failed["run_id"])
        return self.complete(resumed["run_id"])

    def heartbeat(self, run_id: str, *, fence: str | None = None) -> dict[str, Any]:
        row = self._require(run_id)
        if str(row["status"]) not in ACTIVE:
            raise ValueError("heartbeat denied unless the run is active")
        now = self._attestation_now(str(row["stage"]))
        self._detect_integrity(row, now, fence)
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
            self._append_event(run_id, "HEARTBEAT", "RUNNING", {"elapsed": elapsed}, now)
        return self.get(run_id)

    def resume(self, run_id: str, *, process_id: int | None = None) -> dict[str, Any]:
        row = self._require(run_id)
        if str(row["status"]) not in {"RUNNING", "RESUMED", "FAILED", "DISQUALIFIED"}:
            raise ValueError("only an interrupted, failed, or disqualified run can resume")
        now = self._attestation_now(str(row["stage"]))
        broken = 1 if str(row["stage"]) in {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"} else 0
        with self._db:
            self._db.execute(
                "DELETE FROM qualification_locks WHERE lock_name = 'active-qualification'"
            )
            self._db.execute(
                """
                UPDATE qualification_runs
                SET process_id = ?, last_heartbeat_utc = ?, status = 'RESUMED', window_broken = ?
                WHERE run_id = ?
                """,
                (
                    int(process_id if process_id is not None else os.getpid()),
                    now.isoformat(),
                    broken,
                    run_id,
                ),
            )
            self._db.execute(
                """
                INSERT INTO qualification_locks (lock_name, run_id, process_id, fence, acquired_at_utc)
                VALUES ('active-qualification', ?, ?, ?, ?)
                """,
                (
                    run_id,
                    int(process_id if process_id is not None else os.getpid()),
                    str(row["fence"]),
                    now.isoformat(),
                ),
            )
            self._append_event(run_id, "RESUME", "RESUMED", {"window_broken": broken}, now)
        return self.get(run_id)

    def fail(self, run_id: str, *, reason: str) -> dict[str, Any]:
        return self._halt(run_id, "FAILED", f"FAIL:{reason}")

    def stop(self, run_id: str, *, reason: str = "autonomy-stop") -> dict[str, Any]:
        return self._halt(run_id, "STOPPED", f"STOP:{reason}")

    def complete(self, run_id: str) -> dict[str, Any]:
        row = self._require(run_id)
        if str(row["status"]) == "ATTESTED":
            return self.get(run_id)
        stage = str(row["stage"])
        now = self._attestation_now(stage)
        if int(row["window_broken"]) == 1 and stage in {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"}:
            raise ValueError("uninterrupted window was broken and cannot be accumulated")
        elapsed = self._elapsed_seconds(row, now)
        required = H24 if stage == "UNATTENDED_24_HOUR" else H72
        if (
            stage in {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"}
            and elapsed < required.total_seconds()
        ):
            raise ValueError("elapsed time cannot be simulated or shortened")
        if stage == "UNATTENDED_72_HOUR" and not self._twenty_four_hour_attested():
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
            self._db.execute("DELETE FROM qualification_locks WHERE run_id = ?", (run_id,))
            self._append_event(run_id, "ATTEST", "ATTESTED", {"elapsed": elapsed}, now)
        return self.get(run_id)

    def orchestrate(self, run_id: str, commands: list[list[str]]) -> dict[str, Any]:
        from project_pipeline.autonomy_runtime.command_execution import (
            execute_allowlisted_command,
        )

        row = self._require(run_id)
        now = self._attestation_now(str(row["stage"]))
        receipts = []
        for command in commands:
            receipt = execute_allowlisted_command(
                [str(item) for item in command],
                cwd=self.repository_root,
                repository_root=self.repository_root,
            )
            receipts.append(receipt)
        with self._db:
            self._append_event(
                run_id, "ORCHESTRATE", str(row["status"]), {"receipts": receipts}, now
            )
        return {"run_id": run_id, "orchestration_receipts": receipts}

    def run_loop(
        self, run_id: str, *, cycles: int = 1, stop_path: Path | None = None
    ) -> dict[str, Any]:
        last = self.get(run_id)
        for _ in range(max(1, cycles)):
            if stop_path is not None and stop_path.exists():
                return self.stop(run_id, reason="stop-file")
            last = self.heartbeat(run_id)
            time.sleep(min(self.heartbeat_seconds, 0.05) if self.heartbeat_seconds < 1 else 0)
        return last

    def health(self, run_id: str) -> dict[str, Any]:
        row = self.get(run_id)
        now = self._attestation_now(str(row["stage"]))
        return {
            **row,
            "elapsed_seconds": self._elapsed_seconds(self._require(run_id), now),
            "stop_command": [
                "python",
                "scripts/run_autonomy_qualification.py",
                "stop",
                "--database",
                str(self.path),
                "--run-id",
                run_id,
            ],
            "resume_command": [
                "python",
                "scripts/run_autonomy_qualification.py",
                "resume",
                "--database",
                str(self.path),
                "--run-id",
                run_id,
            ],
            "simulated_elapsed": False,
        }

    def get(self, run_id: str) -> dict[str, Any]:
        return dict(self._require(run_id))

    def _halt(self, run_id: str, status: str, action: str) -> dict[str, Any]:
        row = self._require(run_id)
        now = self._attestation_now(str(row["stage"]))
        elapsed = self._elapsed_seconds(row, now)
        with self._db:
            self._db.execute(
                """
                UPDATE qualification_runs
                SET status = ?, attested_elapsed_seconds = ?, last_heartbeat_utc = ?
                WHERE run_id = ?
                """,
                (status, elapsed, now.isoformat(), run_id),
            )
            self._db.execute("DELETE FROM qualification_locks WHERE run_id = ?", (run_id,))
            self._append_event(run_id, action, status, {"elapsed": elapsed}, now)
        return self.get(run_id)

    def _detect_integrity(self, row: sqlite3.Row, now: datetime, fence: str | None) -> None:
        if fence is not None and fence != str(row["fence"]):
            self._disqualify(str(row["run_id"]), "fence-mismatch")
            raise ValueError("qualification fence mismatch")
        last = datetime.fromisoformat(str(row["last_heartbeat_utc"]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if now < last:
            self._disqualify(str(row["run_id"]), "clock-rollback")
            raise ValueError("clock rollback detected")
        cadence = float(row["heartbeat_cadence_seconds"])
        gap = (now - last).total_seconds()
        if str(row["stage"]) in {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"} and gap > max(
            cadence * 3, cadence + 1
        ):
            self._disqualify(str(row["run_id"]), "heartbeat-gap")
            raise ValueError("heartbeat gap broke the uninterrupted window")
        lock = self._db.execute(
            "SELECT * FROM qualification_locks WHERE lock_name = 'active-qualification'"
        ).fetchone()
        if lock is not None and str(lock["fence"]) != str(row["fence"]):
            self._disqualify(str(row["run_id"]), "lock-fence-mismatch")
            raise ValueError("qualification lock fence mismatch")
        expected = str(row["last_event_sha256"] or "")
        latest = self._db.execute(
            "SELECT event_sha256 FROM qualification_events WHERE run_id = ? ORDER BY created_at_utc DESC LIMIT 1",
            (str(row["run_id"]),),
        ).fetchone()
        if latest is not None and expected and str(latest["event_sha256"]) != expected:
            self._disqualify(str(row["run_id"]), "event-chain-break")
            raise ValueError("qualification event chain was edited or rolled back")

    def _disqualify(self, run_id: str, reason: str) -> None:
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE qualification_runs
                SET status = 'DISQUALIFIED', window_broken = 1
                WHERE run_id = ?
                """,
                (run_id,),
            )
            self._db.execute("DELETE FROM qualification_locks WHERE run_id = ?", (run_id,))
            self._append_event(
                run_id, f"DISQUALIFY:{reason}", "DISQUALIFIED", {"reason": reason}, now
            )

    def _reject_concurrent_lock(self) -> None:
        lock = self._db.execute(
            "SELECT * FROM qualification_locks WHERE lock_name = 'active-qualification'"
        ).fetchone()
        if lock is None:
            return
        if _pid_alive(int(lock["process_id"])):
            raise ValueError("concurrent qualification runner is already active")
        with self._db:
            self._db.execute(
                "DELETE FROM qualification_locks WHERE lock_name = 'active-qualification'"
            )

    def _attestation_now(self, stage: str) -> datetime:
        if stage in {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"}:
            return datetime.now(UTC)
        return self.clock.now()

    def _twenty_four_hour_attested(self) -> bool:
        row = self._db.execute(
            """
            SELECT attested_elapsed_seconds, window_broken FROM qualification_runs
            WHERE stage = 'UNATTENDED_24_HOUR' AND status = 'ATTESTED'
            ORDER BY started_at_utc DESC LIMIT 1
            """
        ).fetchone()
        return (
            row is not None
            and int(row["window_broken"]) == 0
            and float(row["attested_elapsed_seconds"]) >= H24.total_seconds()
        )

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

    def _append_event(
        self,
        run_id: str,
        action: str,
        status: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        previous = self._db.execute(
            "SELECT last_event_sha256 FROM qualification_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        prev_hash = None if previous is None else previous["last_event_sha256"]
        body = {
            "run_id": run_id,
            "action": action,
            "status": status,
            "payload": payload,
            "prev_event_sha256": prev_hash,
            "created_at_utc": now.isoformat(),
        }
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        event_id = "QEVT-" + digest[:16]
        self._db.execute(
            """
            INSERT INTO qualification_events (
                event_id, run_id, action, status, payload_json, prev_event_sha256,
                event_sha256, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                run_id,
                action,
                status,
                json.dumps(payload, sort_keys=True),
                prev_hash,
                digest,
                now.isoformat(),
            ),
        )
        self._db.execute(
            "UPDATE qualification_runs SET last_event_sha256 = ? WHERE run_id = ?",
            (digest, run_id),
        )


QualificationService = QualificationStore
