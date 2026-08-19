from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from project_pipeline.autonomy_runtime.command_execution import execute_allowlisted_command
from project_pipeline.autonomy_runtime.qualification import (
    ACTIVE,
    QualificationStore,
    SystemClock,
    _pid_alive,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner

CAMPAIGN_STAGES = (
    "RECOVERY",
    "UNATTENDED_24_HOUR",
    "UNATTENDED_72_HOUR",
    "RELEASE",
    "POST_RELEASE",
    "COMPLETION_GATE",
    "CLEANUP",
    "COMPLETE",
)
REQUIRED_PP384_STAGES = (
    "windows_service_foreground",
    "command_center_truth",
    "local_provider_dispatch",
    "github_jira_governance",
    "cursor_cli_provider_dispatch",
)
REQUIRED_TABLES = (
    "campaign_runs",
    "campaign_events",
    "campaign_command_receipts",
    "campaign_locks",
)
TIMED_STAGES = {"UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"}
IdentityInspector = Callable[[Path], dict[str, Any]]


def inspect_worktree_identity(root: Path) -> dict[str, Any]:
    def git(*args: str) -> tuple[int, str]:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        return int(completed.returncode), (completed.stdout or "").strip()

    head_rc, sha = git("rev-parse", "HEAD")
    tree_rc, tree = git("rev-parse", "HEAD^{tree}")
    status_rc, porcelain = git("status", "--porcelain")
    dirty = bool(porcelain)
    return {
        "sha": sha,
        "tree": tree,
        "dirty": dirty,
        "ok": head_rc == 0 and tree_rc == 0 and status_rc == 0 and bool(sha) and bool(tree),
    }


def evaluate_pp384_admission(evidence_path: Path) -> dict[str, Any]:
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    stages = {
        str(item.get("stage_id")): str(item.get("outcome"))
        for item in payload.get("stages", [])
        if isinstance(item, dict)
    }
    missing = [stage for stage in REQUIRED_PP384_STAGES if stages.get(stage) != "PASSED"]
    return {
        "admitted": not missing,
        "missing": missing,
        "task_id": payload.get("task_id"),
        "stages": stages,
    }


class CampaignController:
    """Durable unattended campaign state machine. Elapsed time is never simulated."""

    def __init__(
        self,
        path: Path,
        *,
        repository_root: Path,
        clock: Any | None = None,
        heartbeat_seconds: float = 30.0,
        inspect_identity: IdentityInspector | None = None,
    ) -> None:
        self.path = path
        self.repository_root = repository_root.resolve()
        self.clock = clock or SystemClock()
        self.heartbeat_seconds = float(heartbeat_seconds)
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat cadence must be positive")
        self._inspect_identity = inspect_identity or inspect_worktree_identity
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.qualification = QualificationStore(
            path,
            clock=self.clock,
            repository_root=self.repository_root,
            heartbeat_seconds=self.heartbeat_seconds,
        )
        self._db = self.qualification._db
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
                "campaign schema is missing catalog tables "
                f"{missing}; apply PPDB-0022 rather than creating tables ad hoc"
            )

    def close(self) -> None:
        self.qualification.close()

    def start(
        self,
        *,
        state_path: Path,
        evidence_path: Path,
        pp384_evidence: Path,
        retry_budget: int = 3,
        process_id: int | None = None,
        service_identity: str | None = None,
        prior_campaign_id: str | None = None,
    ) -> dict[str, Any]:
        identity = self._require_clean_identity()
        admission = evaluate_pp384_admission(pp384_evidence)
        if not admission["admitted"]:
            raise ValueError("campaign start requires PP-384 integrated-main qualification PASSED")
        self._reject_concurrent_lock()
        now = datetime.now(UTC)
        release_identity = f"REL-{identity['sha'][:12]}-{identity['tree'][:12]}"
        payload = {
            "integrated_sha": identity["sha"],
            "integrated_tree": identity["tree"],
            "started_at_utc": now.isoformat(),
            "state_path": str(state_path),
        }
        campaign_id = (
            "QCAMP-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        )
        fence = "CFENCE-" + hashlib.sha256(campaign_id.encode()).hexdigest()[:12]
        lease_id = "CLEASE-" + hashlib.sha256((campaign_id + fence).encode()).hexdigest()[:12]
        lock_token = (
            "CLOCK-" + hashlib.sha256((campaign_id + str(os.getpid())).encode()).hexdigest()[:12]
        )
        pid = int(process_id if process_id is not None else os.getpid())
        with self._db:
            self._db.execute(
                """
                INSERT INTO campaign_runs (
                    campaign_id, integrated_sha, integrated_tree, release_identity, stage,
                    qualification_run_id, fence, lease_id, process_id, service_identity,
                    state_path, last_event_sha256, started_at_utc, last_heartbeat_utc,
                    next_transition, retry_budget, last_probe, evidence_path,
                    pp384_evidence_path, status, window_broken, prior_campaign_id, lock_token
                ) VALUES (?, ?, ?, ?, 'RECOVERY', NULL, ?, ?, ?, ?, ?, NULL, ?, ?,
                          'UNATTENDED_24_HOUR', ?, NULL, ?, ?, 'RUNNING', 0, ?, ?)
                """,
                (
                    campaign_id,
                    identity["sha"],
                    identity["tree"],
                    release_identity,
                    fence,
                    lease_id,
                    pid,
                    service_identity,
                    str(state_path),
                    now.isoformat(),
                    now.isoformat(),
                    int(retry_budget),
                    str(evidence_path),
                    str(pp384_evidence),
                    prior_campaign_id,
                    lock_token,
                ),
            )
            self._db.execute(
                """
                INSERT INTO campaign_locks (lock_name, campaign_id, process_id, fence, acquired_at_utc)
                VALUES ('active-campaign', ?, ?, ?, ?)
                """,
                (campaign_id, pid, fence, now.isoformat()),
            )
            self._append_event(
                campaign_id,
                "START",
                "RUNNING",
                {"stage": "RECOVERY", "admission": admission},
                now,
            )
        attested = self.qualification.recovery_drill(state_path=state_path)
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET qualification_run_id = ?, status = 'ATTESTED', last_heartbeat_utc = ?,
                    last_probe = ?
                WHERE campaign_id = ?
                """,
                (
                    attested["run_id"],
                    now.isoformat(),
                    "recovery-drill-attested",
                    campaign_id,
                ),
            )
            self._append_event(
                campaign_id,
                "RECOVERY_ATTEST",
                "ATTESTED",
                {"qualification_run_id": attested["run_id"]},
                now,
            )
        return self.get(campaign_id)

    def admit_24h(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        self._assert_identity(row)
        if str(row["stage"]) != "RECOVERY" or str(row["status"]) != "ATTESTED":
            raise ValueError("24-hour admission requires an attested recovery drill")
        admission = evaluate_pp384_admission(Path(str(row["pp384_evidence_path"])))
        if not admission["admitted"]:
            raise ValueError(
                "24-hour admission requires PP-384 integrated-main qualification PASSED"
            )
        started = self.qualification.start(
            "UNATTENDED_24_HOUR",
            state_path=Path(str(row["state_path"])),
            prior_run_id=str(row["qualification_run_id"]) if row["qualification_run_id"] else None,
        )
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'UNATTENDED_24_HOUR', qualification_run_id = ?, status = 'RUNNING',
                    next_transition = 'UNATTENDED_72_HOUR', last_heartbeat_utc = ?,
                    last_probe = ?
                WHERE campaign_id = ?
                """,
                (
                    started["run_id"],
                    now.isoformat(),
                    "24h-admitted",
                    campaign_id,
                ),
            )
            self._append_event(
                campaign_id,
                "ADMIT_24H",
                "RUNNING",
                {"qualification_run_id": started["run_id"]},
                now,
            )
        return self.get(campaign_id)

    def admit_72h(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        self._assert_identity(row)
        if not self.qualification._twenty_four_hour_attested():
            raise ValueError("72-hour admission requires a prior attested 24-hour run")
        self.qualification._db.execute(
            "DELETE FROM qualification_locks WHERE lock_name = 'active-qualification'"
        )
        self.qualification._db.commit()
        started = self.qualification.start(
            "UNATTENDED_72_HOUR",
            state_path=Path(str(row["state_path"])),
            prior_run_id=str(row["qualification_run_id"]) if row["qualification_run_id"] else None,
        )
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'UNATTENDED_72_HOUR', qualification_run_id = ?, status = 'RUNNING',
                    next_transition = 'RELEASE', last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (started["run_id"], now.isoformat(), "72h-admitted", campaign_id),
            )
            self._append_event(
                campaign_id,
                "ADMIT_72H",
                "RUNNING",
                {"qualification_run_id": started["run_id"]},
                now,
            )
        return self.get(campaign_id)

    def heartbeat(self, campaign_id: str, *, fence: str | None = None) -> dict[str, Any]:
        row = self._require(campaign_id)
        if fence is not None and fence != str(row["fence"]):
            self._disqualify(campaign_id, "fence-mismatch")
            raise ValueError("campaign fence mismatch")
        self._assert_identity(row)
        now = datetime.now(UTC)
        last = datetime.fromisoformat(str(row["last_heartbeat_utc"]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if now < last:
            self._disqualify(campaign_id, "clock-rollback")
            raise ValueError("clock rollback detected")
        qual_status = None
        if row["qualification_run_id"] and str(row["stage"]) in TIMED_STAGES:
            qual = self.qualification.get(str(row["qualification_run_id"]))
            if str(qual["status"]) in ACTIVE:
                qual = self.qualification.heartbeat(
                    str(row["qualification_run_id"]), fence=str(qual["fence"])
                )
            qual_status = qual["status"]
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), f"heartbeat:{qual_status or row['status']}", campaign_id),
            )
            self._append_event(
                campaign_id,
                "HEARTBEAT",
                str(row["status"]),
                {"qualification_status": qual_status},
                now,
            )
        return self.get(campaign_id)

    def advance(self, campaign_id: str) -> dict[str, Any]:
        row = self.get(campaign_id)
        stage = str(row["stage"])
        status = str(row["status"])
        if status in {"DISQUALIFIED", "FAILED", "STOPPED"}:
            return row
        if stage == "RECOVERY" and status == "ATTESTED":
            return self.admit_24h(campaign_id)
        if stage in TIMED_STAGES and row["qualification_run_id"]:
            run_id = str(row["qualification_run_id"])
            try:
                attested = self.qualification.complete(run_id)
            except ValueError:
                return self.heartbeat(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_24_HOUR":
                return self.admit_72h(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_72_HOUR":
                return self._mark_ready_to_finalize(campaign_id)
        return self.heartbeat(campaign_id)

    def recover(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        lock = self._db.execute(
            "SELECT * FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
        if lock is not None and _pid_alive(int(lock["process_id"])):
            raise ValueError("concurrent campaign runner is already active")
        if str(row["stage"]) in TIMED_STAGES:
            run_id = str(row["qualification_run_id"] or "")
            if run_id:
                current = self.qualification.get(run_id)
                if str(current["status"]) in ACTIVE:
                    self.qualification.fail(run_id, reason="stale-runner")
            preserved = self._disqualify(campaign_id, "stale-runner-broken-window")
            budget = int(preserved["retry_budget"])
            if budget <= 0:
                return preserved
            return self.start(
                state_path=Path(str(preserved["state_path"])),
                evidence_path=Path(str(preserved["evidence_path"])),
                pp384_evidence=Path(str(preserved["pp384_evidence_path"])),
                retry_budget=budget - 1,
                service_identity=preserved.get("service_identity"),
                prior_campaign_id=campaign_id,
            )
        now = datetime.now(UTC)
        pid = os.getpid()
        with self._db:
            self._db.execute("DELETE FROM campaign_locks WHERE lock_name = 'active-campaign'")
            self._db.execute(
                """
                INSERT INTO campaign_locks (lock_name, campaign_id, process_id, fence, acquired_at_utc)
                VALUES ('active-campaign', ?, ?, ?, ?)
                """,
                (campaign_id, pid, str(row["fence"]), now.isoformat()),
            )
            self._db.execute(
                "UPDATE campaign_runs SET process_id = ?, last_heartbeat_utc = ? WHERE campaign_id = ?",
                (pid, now.isoformat(), campaign_id),
            )
            self._append_event(campaign_id, "RECOVER", str(row["status"]), {"pid": pid}, now)
        return self.get(campaign_id)

    def execute(
        self,
        campaign_id: str,
        argv: list[str],
        *,
        idempotency_key: str | None = None,
        evidence_links: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require(campaign_id)
        receipt = execute_allowlisted_command(
            argv,
            cwd=self.repository_root,
            repository_root=self.repository_root,
            idempotency_key=idempotency_key,
            evidence_links=evidence_links,
        )
        now = datetime.now(UTC)
        body = {
            "campaign_id": campaign_id,
            "command_sha256": receipt["command_sha256"],
            "idempotency_key": receipt["idempotency_key"],
            "created_at_utc": now.isoformat(),
        }
        receipt_id = (
            "CREC-" + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
        )
        with self._db:
            self._db.execute(
                """
                INSERT INTO campaign_command_receipts (
                    receipt_id, campaign_id, command_json, command_sha256, cwd,
                    started_at_utc, ended_at_utc, exit_code, stdout_sha256, stderr_sha256,
                    stdout_tail, stderr_tail, result, idempotency_key, retry_disposition,
                    evidence_json, executed, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    receipt_id,
                    campaign_id,
                    json.dumps(receipt["command"], sort_keys=True),
                    receipt["command_sha256"],
                    receipt["cwd"],
                    receipt["started_at_utc"],
                    receipt["ended_at_utc"],
                    receipt["exit_code"],
                    receipt["stdout_sha256"],
                    receipt["stderr_sha256"],
                    receipt["stdout_tail"],
                    receipt["stderr_tail"],
                    receipt["result"],
                    receipt["idempotency_key"],
                    receipt["retry_disposition"],
                    json.dumps(receipt["evidence_links"], sort_keys=True),
                    now.isoformat(),
                ),
            )
            self._append_event(
                campaign_id,
                "EXECUTE",
                str(self._require(campaign_id)["status"]),
                {"receipt_id": receipt_id, "result": receipt["result"]},
                now,
            )
        return {**receipt, "receipt_id": receipt_id, "campaign_id": campaign_id}

    def finalize(self, campaign_id: str, commands: list[list[str]] | None = None) -> dict[str, Any]:
        row = self._require(campaign_id)
        if str(row["stage"]) != "RELEASE" or str(row["status"]) != "READY_TO_FINALIZE":
            raise ValueError("finalize requires an attested 72-hour campaign ready for release")
        planned = commands or [
            [
                self._python(),
                "-m",
                "project_pipeline",
                "completion",
                "--root",
                str(self.repository_root),
            ],
            [
                self._python(),
                "-m",
                "project_pipeline",
                "validate",
                "--root",
                str(self.repository_root),
            ],
        ]
        receipts = []
        for argv in planned:
            receipts.append(self.execute(campaign_id, argv))
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'COMPLETE', status = 'FINALIZED', next_transition = NULL,
                    last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), "finalize-executed", campaign_id),
            )
            self._append_event(
                campaign_id,
                "FINALIZE",
                "FINALIZED",
                {"receipts": [item["receipt_id"] for item in receipts]},
                now,
            )
        result = self.get(campaign_id)
        result["finalization_receipts"] = receipts
        return result

    def run_loop(
        self,
        campaign_id: str,
        *,
        cycles: int = 0,
        stop_path: Path | None = None,
    ) -> dict[str, Any]:
        last = self.get(campaign_id)
        count = 0
        while True:
            if stop_path is not None and stop_path.exists():
                return self.stop(campaign_id, reason="stop-file")
            last = self.advance(campaign_id)
            count += 1
            if cycles > 0 and count >= cycles:
                return last
            if last["status"] in {"FINALIZED", "DISQUALIFIED", "FAILED", "STOPPED"}:
                return last
            time.sleep(self.heartbeat_seconds)

    def stop(self, campaign_id: str, *, reason: str = "autonomy-stop") -> dict[str, Any]:
        row = self._require(campaign_id)
        if row["qualification_run_id"]:
            current = self.qualification.get(str(row["qualification_run_id"]))
            if str(current["status"]) in ACTIVE:
                self.qualification.stop(str(row["qualification_run_id"]), reason=reason)
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                "UPDATE campaign_runs SET status = 'STOPPED', last_heartbeat_utc = ? WHERE campaign_id = ?",
                (now.isoformat(), campaign_id),
            )
            self._db.execute("DELETE FROM campaign_locks WHERE campaign_id = ?", (campaign_id,))
            self._append_event(campaign_id, f"STOP:{reason}", "STOPPED", {"reason": reason}, now)
        return self.get(campaign_id)

    def health(self, campaign_id: str) -> dict[str, Any]:
        row = self.get(campaign_id)
        identity = self._inspect_identity(self.repository_root)
        drift = (
            identity.get("sha") != row["integrated_sha"]
            or identity.get("tree") != row["integrated_tree"]
            or bool(identity.get("dirty"))
        )
        return {
            **row,
            "identity": identity,
            "identity_drift": drift,
            "simulated_elapsed": False,
            "stop_command": [
                self._python(),
                str(self.repository_root / "scripts/run_autonomy_campaign.py"),
                "stop",
                "--database",
                str(self.path),
                "--campaign-id",
                campaign_id,
            ],
            "resume_command": [
                self._python(),
                str(self.repository_root / "scripts/run_autonomy_campaign.py"),
                "recover",
                "--database",
                str(self.path),
                "--campaign-id",
                campaign_id,
            ],
        }

    def get(self, campaign_id: str) -> dict[str, Any]:
        return dict(self._require(campaign_id))

    def receipts(self, campaign_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT * FROM campaign_command_receipts
            WHERE campaign_id = ? ORDER BY created_at_utc
            """,
            (campaign_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _mark_ready_to_finalize(self, campaign_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'RELEASE', status = 'READY_TO_FINALIZE',
                    next_transition = 'POST_RELEASE', last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), "72h-attested", campaign_id),
            )
            self._append_event(campaign_id, "READY_TO_FINALIZE", "READY_TO_FINALIZE", {}, now)
        return self.get(campaign_id)

    def _require_clean_identity(self) -> dict[str, Any]:
        identity = self._inspect_identity(self.repository_root)
        if not identity.get("ok"):
            raise ValueError("campaign cannot inspect a pinned worktree identity")
        if identity.get("dirty"):
            raise ValueError("campaign requires a clean immutable worktree")
        return identity

    def _assert_identity(self, row: sqlite3.Row | dict[str, Any]) -> None:
        identity = self._inspect_identity(self.repository_root)
        if (
            identity.get("sha") != str(row["integrated_sha"])
            or identity.get("tree") != str(row["integrated_tree"])
            or identity.get("dirty")
        ):
            self._disqualify(str(row["campaign_id"]), "identity-drift")
            raise ValueError("campaign worktree identity drifted from the pinned release candidate")

    def _disqualify(self, campaign_id: str, reason: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET status = 'DISQUALIFIED', window_broken = 1, last_heartbeat_utc = ?,
                    last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), f"disqualify:{reason}", campaign_id),
            )
            self._db.execute("DELETE FROM campaign_locks WHERE campaign_id = ?", (campaign_id,))
            self._append_event(
                campaign_id, f"DISQUALIFY:{reason}", "DISQUALIFIED", {"reason": reason}, now
            )
        return self.get(campaign_id)

    def _reject_concurrent_lock(self) -> None:
        lock = self._db.execute(
            "SELECT * FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
        if lock is None:
            return
        if _pid_alive(int(lock["process_id"])):
            raise ValueError("concurrent campaign runner is already active")
        with self._db:
            self._db.execute("DELETE FROM campaign_locks WHERE lock_name = 'active-campaign'")

    def _require(self, campaign_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM campaign_runs WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown campaign: {campaign_id}")
        return cast(sqlite3.Row, row)

    def _python(self) -> str:
        return str(Path(__import__("sys").executable))

    def _append_event(
        self,
        campaign_id: str,
        action: str,
        status: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        previous = self._db.execute(
            "SELECT last_event_sha256 FROM campaign_runs WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        prev_hash = None if previous is None else previous["last_event_sha256"]
        body = {
            "campaign_id": campaign_id,
            "action": action,
            "status": status,
            "payload": payload,
            "prev_event_sha256": prev_hash,
            "created_at_utc": now.isoformat(),
        }
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        event_id = "CEVT-" + digest[:16]
        self._db.execute(
            """
            INSERT INTO campaign_events (
                event_id, campaign_id, action, status, payload_json, prev_event_sha256,
                event_sha256, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                campaign_id,
                action,
                status,
                json.dumps(payload, sort_keys=True),
                prev_hash,
                digest,
                now.isoformat(),
            ),
        )
        self._db.execute(
            "UPDATE campaign_runs SET last_event_sha256 = ? WHERE campaign_id = ?",
            (digest, campaign_id),
        )
