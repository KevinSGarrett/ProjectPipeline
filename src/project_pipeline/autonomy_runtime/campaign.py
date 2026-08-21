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

from project_pipeline.autonomy_runtime.campaign_status import (
    build_status_projection,
    write_status_projection,
)
from project_pipeline.autonomy_runtime.command_execution import (
    command_kind,
    execute_allowlisted_command,
)
from project_pipeline.autonomy_runtime.process_identity import (
    current_process_identity,
    identities_match,
    inspect_process,
)
from project_pipeline.autonomy_runtime.qualification import (
    ACTIVE,
    H4,
    H24,
    TIMED_STAGES,
    QualificationStore,
    SystemClock,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner

CAMPAIGN_STAGES = (
    "RECOVERY",
    "UNATTENDED_4_HOUR",
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
    "campaign_owner_bindings",
)
TABLE_INTRODUCED_BY = {
    "campaign_runs": "PPDB-0022",
    "campaign_events": "PPDB-0022",
    "campaign_command_receipts": "PPDB-0022",
    "campaign_locks": "PPDB-0022",
    "campaign_owner_bindings": "PPDB-0023",
}
REQUIRED_CAMPAIGN_MIGRATION = "PPDB-0023"
IdentityInspector = Callable[[Path], dict[str, Any]]


class CampaignSchemaError(RuntimeError):
    """Legacy or incomplete campaign schema. Next action is machine-owned."""

    def __init__(self, missing: list[str], required_migrations: list[str]) -> None:
        self.missing = tuple(missing)
        self.required_migrations = tuple(required_migrations)
        self.next_action = {
            "owner": "campaign.controller",
            "action": "apply_catalog_migrations",
            "target_migrations": self.required_migrations,
            "user_action_required": False,
            "ad_hoc_tables_forbidden": True,
        }
        super().__init__(
            "campaign schema is missing catalog tables "
            f"{list(self.missing)}; required catalog migration(s) "
            f"{list(self.required_migrations)}; next_action=apply_catalog_migrations; "
            "do not create tables ad hoc"
        )


def required_migrations_for_missing_tables(missing: list[str]) -> list[str]:
    required: list[str] = []
    for name in missing:
        migration_id = TABLE_INTRODUCED_BY.get(name)
        if migration_id and migration_id not in required:
            required.append(migration_id)
    if not required and missing:
        required.append(REQUIRED_CAMPAIGN_MIGRATION)
    return required


def classify_campaign_database(connection: sqlite3.Connection) -> dict[str, Any]:
    """Classify a campaign database against the current catalog. Never mutates."""

    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    latest = None
    if "schema_migrations" in tables:
        row = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id DESC LIMIT 1"
        ).fetchone()
        latest = None if row is None else str(row[0])
    missing = [name for name in REQUIRED_TABLES if name not in tables]
    required = required_migrations_for_missing_tables(missing)
    migration_required = bool(missing) or (
        latest is not None and latest < REQUIRED_CAMPAIGN_MIGRATION
    )
    return {
        "latest_applied": latest,
        "required_latest": REQUIRED_CAMPAIGN_MIGRATION,
        "missing_tables": missing,
        "required_migrations": required,
        "migration_required": migration_required,
        "next_action": {
            "owner": "campaign.controller",
            "action": "apply_catalog_migrations" if migration_required else "none",
            "target_migrations": required
            if required
            else ([REQUIRED_CAMPAIGN_MIGRATION] if migration_required else []),
            "user_action_required": False,
            "ad_hoc_tables_forbidden": True,
        },
        "user_action_required": False,
    }


def legacy_non_final_import_receipt(
    *,
    campaign_id: str,
    integrated_sha: str,
    integrated_tree: str,
    source_database: str,
    latest_applied: str | None,
    elapsed_observations_retained: bool = True,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "receipt_kind": "legacy_non_final_import_archive",
        "campaign_id": campaign_id,
        "integrated_sha": integrated_sha,
        "integrated_tree": integrated_tree,
        "source_database": source_database,
        "latest_applied": latest_applied,
        "elapsed_observations_retained": elapsed_observations_retained,
        "qualifies_release": False,
        "admits_72_hour": False,
        "admits_finalization": False,
        "user_action_required": False,
        "reason": (
            "legacy campaign observations may be retained but cannot qualify a "
            "different integrated subject or a later release candidate"
        ),
    }


def evaluate_campaign_aware_health(
    *,
    campaign: dict[str, Any],
    owner_binding: dict[str, Any] | None = None,
    pid_identity: dict[str, Any] | None = None,
    qualification_owner_live: dict[str, Any] | None = None,
    campaign_lock_live: dict[str, Any] | None = None,
    expected_sha: str = "",
    expected_tree: str = "",
    expected_fence: str = "",
    heartbeat_max_age_seconds: float = 90.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Classify campaign health. PID existence alone is never sufficient."""

    reasons: list[str] = []
    current = now or datetime.now(UTC)
    status = str(campaign.get("status") or "")
    if status not in {"RUNNING", "ATTESTED", "READY_TO_FINALIZE"}:
        reasons.append("inactive_status")
    last = campaign.get("last_heartbeat_utc")
    heartbeat_fresh = False
    if not last:
        reasons.append("heartbeat_missing")
    else:
        stamp = datetime.fromisoformat(str(last))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        heartbeat_fresh = (current - stamp).total_seconds() <= float(heartbeat_max_age_seconds)
        if not heartbeat_fresh:
            reasons.append("stale_heartbeat")
    if expected_sha and str(campaign.get("integrated_sha") or "") != expected_sha:
        reasons.append("sha_mismatch")
    if expected_tree and str(campaign.get("integrated_tree") or "") != expected_tree:
        reasons.append("tree_mismatch")
    if expected_fence and str(campaign.get("fence") or "") != expected_fence:
        reasons.append("fence_mismatch")

    binding_complete = bool(
        owner_binding
        and str(owner_binding.get("executable_identity") or "").strip()
        and str(owner_binding.get("process_started_at_utc") or "").strip()
    )
    pid_only = bool(
        pid_identity
        and pid_identity.get("process_id")
        and not str(pid_identity.get("executable") or "").strip()
        and not str(pid_identity.get("started_at_utc") or "").strip()
        and not binding_complete
    )
    if pid_only and qualification_owner_live is None:
        reasons.append("pid_only_insufficient")

    qual_live = bool(
        qualification_owner_live is not None and qualification_owner_live.get("alive") is not False
    )
    lock_live = bool(
        campaign_lock_live is not None and campaign_lock_live.get("alive") is not False
    )

    if lock_live and (binding_complete or (pid_identity or {}).get("executable")):
        bound = {
            "process_id": int(
                (campaign_lock_live or {}).get("process_id")
                or (pid_identity or {}).get("process_id")
                or campaign.get("process_id")
                or 0
            ),
            "executable": (
                (owner_binding or {}).get("executable_identity")
                or (pid_identity or {}).get("executable")
            ),
            "started_at_utc": (
                (owner_binding or {}).get("process_started_at_utc")
                or (pid_identity or {}).get("started_at_utc")
            ),
        }
        if (
            bound.get("executable")
            and bound.get("started_at_utc")
            and not identities_match(bound, campaign_lock_live)
        ):
            reasons.append("pid_reuse")

    identity_mismatch = bool(
        {"sha_mismatch", "tree_mismatch", "fence_mismatch", "inactive_status"} & set(reasons)
    )
    owner_kind = "none"
    if qual_live and heartbeat_fresh and not identity_mismatch:
        owner_kind = "process_chain" if lock_live else "qualification_child"
    elif (
        lock_live
        and heartbeat_fresh
        and binding_complete
        and "pid_reuse" not in reasons
        and not identity_mismatch
    ):
        owner_kind = "campaign_lock"
    if owner_kind == "none" and not qual_live and not lock_live:
        reasons.append("no_live_owner")

    blocking = {
        "inactive_status",
        "stale_heartbeat",
        "heartbeat_missing",
        "sha_mismatch",
        "tree_mismatch",
        "fence_mismatch",
        "pid_only_insufficient",
        "pid_reuse",
    }
    healthy = owner_kind != "none" and not blocking.intersection(reasons)
    return {
        "healthy": healthy,
        "owner_kind": owner_kind,
        "reasons": reasons,
        "live_owner_kinds": (
            (("qualification",) if qual_live else ()) + (("campaign_lock",) if lock_live else ())
        ),
        "user_action_required": False,
    }


def observe_windows_scheduled_task(
    task_name: str,
    *,
    runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Observe a Windows scheduled task. Absence is not a human instruction."""

    invoke = runner or subprocess.run
    completed = invoke(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "(Get-ScheduledTask -TaskName '"
                + task_name.replace("'", "''")
                + "' -ErrorAction SilentlyContinue).TaskName"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    observed = (getattr(completed, "stdout", None) or "").strip()
    observed_name = observed.splitlines()[0].strip() if observed else ""
    present = bool(observed_name) and observed_name.casefold() == task_name.casefold()
    return {
        "task_name": task_name,
        "present": present,
        "observed_name": observed_name,
        "user_action_required": False,
        "next_action": "none" if present else "defer_register_until_release_candidate",
    }


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
        finalize_commands: list[list[str]] | None = None,
    ) -> None:
        self.path = path
        self.repository_root = repository_root.resolve()
        self.clock = clock or SystemClock()
        self.heartbeat_seconds = float(heartbeat_seconds)
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat cadence must be positive")
        self._inspect_identity = inspect_identity or inspect_worktree_identity
        self._finalize_commands = finalize_commands
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
            raise CampaignSchemaError(missing, required_migrations_for_missing_tables(missing))

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
                          'UNATTENDED_4_HOUR', ?, NULL, ?, ?, 'RUNNING', 0, ?, ?)
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
            owner = current_process_identity(service_identity=service_identity)
            owner["process_id"] = pid
            self._upsert_owner_binding(
                campaign_id,
                owner,
                {
                    "qualification_run_id": None,
                    "fence": fence,
                    "lease_id": lease_id,
                    "service_identity": service_identity,
                },
                now,
                reason="bootstrap",
            )
            self._append_event(
                campaign_id,
                "START",
                "RUNNING",
                {
                    "stage": "RECOVERY",
                    "next": "UNATTENDED_4_HOUR",
                    "admission": admission,
                    "bootstrap_pid": pid,
                },
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

    def admit_4h(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        self._assert_identity(row)
        if str(row["stage"]) != "RECOVERY" or str(row["status"]) != "ATTESTED":
            raise ValueError("4-hour admission requires an attested recovery drill")
        admission = evaluate_pp384_admission(Path(str(row["pp384_evidence_path"])))
        if not admission["admitted"]:
            raise ValueError(
                "4-hour admission requires PP-384 integrated-main qualification PASSED"
            )
        started = self.qualification.start(
            "UNATTENDED_4_HOUR",
            state_path=Path(str(row["state_path"])),
            prior_run_id=str(row["qualification_run_id"]) if row["qualification_run_id"] else None,
        )
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'UNATTENDED_4_HOUR', qualification_run_id = ?, status = 'RUNNING',
                    next_transition = 'UNATTENDED_24_HOUR', last_heartbeat_utc = ?,
                    last_probe = ?
                WHERE campaign_id = ?
                """,
                (
                    started["run_id"],
                    now.isoformat(),
                    "4h-admitted",
                    campaign_id,
                ),
            )
            self._append_event(
                campaign_id,
                "ADMIT_4H",
                "RUNNING",
                {"qualification_run_id": started["run_id"]},
                now,
            )
        return self.get(campaign_id)

    def admit_24h(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        self._assert_identity(row)
        if str(row["stage"]) != "UNATTENDED_4_HOUR":
            raise ValueError("24-hour admission requires a prior attested 4-hour run")
        run_id = str(row["qualification_run_id"] or "")
        if not run_id:
            raise ValueError("24-hour admission requires a prior attested 4-hour run")
        four = self.qualification.get(run_id)
        if (
            str(four["stage"]) != "UNATTENDED_4_HOUR"
            or str(four["status"]) != "ATTESTED"
            or int(four["window_broken"]) != 0
            or float(four["attested_elapsed_seconds"]) < H4.total_seconds()
        ):
            raise ValueError("24-hour admission requires a prior attested 4-hour run")
        admission = evaluate_pp384_admission(Path(str(row["pp384_evidence_path"])))
        if not admission["admitted"]:
            raise ValueError(
                "24-hour admission requires PP-384 integrated-main qualification PASSED"
            )
        started = self.qualification.start(
            "UNATTENDED_24_HOUR",
            state_path=Path(str(row["state_path"])),
            prior_run_id=run_id,
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
        if str(row["stage"]) != "UNATTENDED_24_HOUR":
            raise ValueError("72-hour admission requires a prior attested 24-hour run")
        run_id = str(row["qualification_run_id"] or "")
        if not run_id:
            raise ValueError("72-hour admission requires a prior attested 24-hour run")
        day = self.qualification.get(run_id)
        if (
            str(day["stage"]) != "UNATTENDED_24_HOUR"
            or str(day["status"]) != "ATTESTED"
            or int(day["window_broken"]) != 0
            or float(day["attested_elapsed_seconds"]) < H24.total_seconds()
        ):
            raise ValueError("72-hour admission requires a prior attested 24-hour run")
        started = self.qualification.start(
            "UNATTENDED_72_HOUR",
            state_path=Path(str(row["state_path"])),
            prior_run_id=run_id,
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
        self._assert_live_ownership(row, require_current_process=True)
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
        if status in {"DISQUALIFIED", "FAILED", "STOPPED", "FINALIZED"}:
            return row
        if status == "READY_TO_FINALIZE":
            return self.finalize(campaign_id)
        if stage == "RECOVERY" and status == "ATTESTED":
            return self.admit_4h(campaign_id)
        if stage in TIMED_STAGES and row["qualification_run_id"]:
            run_id = str(row["qualification_run_id"])
            try:
                attested = self.qualification.complete(run_id)
            except ValueError:
                return self.heartbeat(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_4_HOUR":
                return self.admit_24h(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_24_HOUR":
                return self.admit_72h(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_72_HOUR":
                self._mark_ready_to_finalize(campaign_id)
                return self.finalize(campaign_id)
        return self.heartbeat(campaign_id)

    def recover(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        lock = self._db.execute(
            "SELECT * FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
        if lock is not None:
            live = inspect_process(int(lock["process_id"]))
            binding = self._owner_binding()
            bound = {
                "process_id": lock["process_id"],
                "executable": None if binding is None else binding.get("executable_identity"),
                "started_at_utc": None
                if binding is None
                else binding.get("process_started_at_utc"),
            }
            if (
                live is not None
                and self._binding_complete(binding)
                and identities_match(bound, live)
            ):
                raise ValueError("concurrent campaign runner is already active")
            # Missing/incomplete binding or a live mismatched PID is reuse:
            # this recover path is the governed takeover. claim_runner refuses it.
        if self._live_qualification_owner_blocks_recover(row):
            raise ValueError(
                "live qualification owner still holds the campaign; "
                "do not recover a parent/child process chain"
            )
        self._assert_identity(row)
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
            started = self.start(
                state_path=Path(str(preserved["state_path"])),
                evidence_path=Path(str(preserved["evidence_path"])),
                pp384_evidence=Path(str(preserved["pp384_evidence_path"])),
                retry_budget=budget - 1,
                service_identity=preserved.get("service_identity"),
                prior_campaign_id=campaign_id,
            )
            return started
        owner = current_process_identity(service_identity=row["service_identity"])
        now = datetime.now(UTC)
        with self._db:
            self._upsert_owner_binding(campaign_id, owner, row, now, reason="governed-recover")
            self._db.execute(
                "UPDATE campaign_runs SET process_id = ?, last_heartbeat_utc = ? WHERE campaign_id = ?",
                (owner["process_id"], now.isoformat(), campaign_id),
            )
            self._append_event(
                campaign_id,
                "RECOVER",
                str(row["status"]),
                {"pid": owner["process_id"], "campaign_id": campaign_id},
                now,
            )
        return self.get(campaign_id)

    def execute(
        self,
        campaign_id: str,
        argv: list[str],
        *,
        idempotency_key: str | None = None,
        evidence_links: list[str] | None = None,
    ) -> dict[str, Any]:
        row = self._require(campaign_id)
        if idempotency_key:
            existing = self._db.execute(
                """
                SELECT * FROM campaign_command_receipts
                WHERE campaign_id = ? AND idempotency_key = ?
                ORDER BY created_at_utc
                """,
                (campaign_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                stored = dict(existing)
                stored["command"] = json.loads(str(stored["command_json"]))
                stored["executed"] = bool(stored["executed"])
                return stored
        self._assert_live_ownership(row, require_current_process=True)
        receipt = execute_allowlisted_command(
            argv,
            cwd=self.repository_root,
            repository_root=self.repository_root,
            idempotency_key=idempotency_key,
            evidence_links=evidence_links,
            expected_sha=str(row["integrated_sha"]),
            expected_tree=str(row["integrated_tree"]),
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
                    json.dumps(
                        {
                            "links": receipt["evidence_links"],
                            "environment_class": receipt.get("environment_class"),
                            "integrated_sha": receipt.get("integrated_sha"),
                            "integrated_tree": receipt.get("integrated_tree"),
                            "result_semantics": receipt.get("result_semantics"),
                            "semantic_state": receipt.get("semantic_state"),
                            "final_completion_gate_satisfied": receipt.get(
                                "final_completion_gate_satisfied"
                            ),
                            "parsed_result": receipt.get("parsed_result"),
                        },
                        sort_keys=True,
                    ),
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
        self._assert_live_ownership(row, require_current_process=True)
        self._assert_identity(row)
        explicit = commands is not None or self._finalize_commands is not None
        planned = commands or self._finalize_commands or self._default_finalize_commands(row)
        receipts = []
        for argv in planned:
            receipts.append(self.execute(campaign_id, argv))
        now = datetime.now(UTC)
        failed = [item for item in receipts if item.get("result") != "PASSED"]
        gate_ok = self._finalization_gate_satisfied(receipts, explicit=explicit)
        if failed or not gate_ok:
            with self._db:
                self._db.execute(
                    """
                    UPDATE campaign_runs
                    SET status = 'FAILED', last_heartbeat_utc = ?, last_probe = ?
                    WHERE campaign_id = ?
                    """,
                    (now.isoformat(), "finalize-command-failed", campaign_id),
                )
                self._append_event(
                    campaign_id,
                    "FINALIZE_FAILED",
                    "FAILED",
                    {
                        "receipts": [item.get("receipt_id") for item in receipts],
                        "failed": [item.get("receipt_id") for item in failed],
                        "gate_ok": gate_ok,
                    },
                    now,
                )
            result = self.get(campaign_id)
            result["finalization_receipts"] = receipts
            return result
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
                {"receipts": [item.get("receipt_id") for item in receipts]},
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
        self.claim_runner_ownership(campaign_id)
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
            self._db.execute(
                "DELETE FROM campaign_owner_bindings WHERE campaign_id = ?", (campaign_id,)
            )
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
            self._db.execute(
                "DELETE FROM campaign_owner_bindings WHERE campaign_id = ?", (campaign_id,)
            )
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
        live = inspect_process(int(lock["process_id"]))
        if live is not None:
            raise ValueError("concurrent campaign runner is already active")
        raise ValueError("stale campaign lock requires recover")

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

    def _default_finalize_commands(
        self, row: sqlite3.Row | dict[str, Any] | None = None
    ) -> list[list[str]]:
        python = self._python()
        root = str(self.repository_root)
        evidence = (
            Path(str(row["evidence_path"]))
            if row is not None and row["evidence_path"]
            else self.repository_root / ".local" / "release"
        )
        identity = (
            str(row["release_identity"])
            if row is not None and row["release_identity"]
            else "REL-local"
        )
        archive = evidence / f"{identity}.zip"
        return [
            [python, "-m", "project_pipeline", "archive", "--root", root, "--output", str(archive)],
            [python, "-m", "project_pipeline", "verify-archive", "--archive", str(archive)],
            [python, "-m", "project_pipeline", "security", "sbom", "--root", root],
            [python, "-m", "project_pipeline", "security", "supply-chain", "--root", root],
            [python, "-m", "project_pipeline", "resilience", "status", "--root", root],
            [python, "-m", "project_pipeline", "validate", "--root", root],
            [python, "-m", "project_pipeline", "jira", "validate", "--root", root],
            [python, "-m", "project_pipeline", "control", "completion", "--root", root],
            [python, "-m", "project_pipeline", "assurance", "completion-gate", "--root", root],
        ]

    def claim_runner_ownership(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        owner = current_process_identity(service_identity=row["service_identity"])
        lock = self._db.execute(
            "SELECT * FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
        if lock is not None and str(lock["campaign_id"]) != campaign_id:
            raise ValueError("active-campaign lock belongs to a different campaign")
        if lock is not None:
            live = inspect_process(int(lock["process_id"]))
            binding = self._owner_binding()
            if live is not None and int(lock["process_id"]) != int(owner["process_id"]):
                bound = binding or {}
                if self._binding_complete(bound) and identities_match(
                    {
                        "process_id": lock["process_id"],
                        "executable": bound.get("executable_identity"),
                        "started_at_utc": bound.get("process_started_at_utc"),
                    },
                    live,
                ):
                    raise ValueError("concurrent campaign runner is already active")
                raise ValueError("active-campaign lock PID was reused; recover is required")
        now = datetime.now(UTC)
        with self._db:
            self._upsert_owner_binding(campaign_id, owner, row, now, reason="runner-claim")
            self._db.execute(
                "UPDATE campaign_runs SET process_id = ?, last_heartbeat_utc = ? WHERE campaign_id = ?",
                (owner["process_id"], now.isoformat(), campaign_id),
            )
            self._append_event(
                campaign_id,
                "CLAIM_RUNNER",
                str(row["status"]),
                {"pid": owner["process_id"], "executable": owner.get("executable")},
                now,
            )
        return self.get(campaign_id)

    def project_status(
        self,
        campaign_id: str,
        *,
        status_path: Path,
        task_health: dict[str, Any] | None = None,
        is_final_release_candidate: bool = False,
    ) -> dict[str, Any]:
        row = self.get(campaign_id)
        lock = self._db.execute(
            "SELECT * FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
        binding = self._owner_binding()
        runner = None
        if lock is not None:
            live = inspect_process(int(lock["process_id"]))
            bound = {
                "process_id": lock["process_id"],
                "executable": None if binding is None else binding.get("executable_identity"),
                "started_at_utc": None
                if binding is None
                else binding.get("process_started_at_utc"),
            }
            matched = live is not None and identities_match(bound, live)
            runner = (live if matched else None) or {
                "process_id": int(lock["process_id"]),
                "alive": False,
                "executable": bound["executable"],
                "started_at_utc": bound["started_at_utc"],
                "identity_match": False,
            }
            if matched:
                runner["alive"] = True
                runner["identity_match"] = True
        payload = build_status_projection(
            campaign=row,
            runner_owner=runner,
            lock=None if lock is None else dict(lock),
            task_health=task_health,
            is_final_release_candidate=is_final_release_candidate,
        )
        return write_status_projection(status_path, payload)

    def current_running_campaigns(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM campaign_runs WHERE status = 'RUNNING' ORDER BY started_at_utc"
        ).fetchall()
        return [dict(row) for row in rows]

    def _finalization_gate_satisfied(
        self, receipts: list[dict[str, Any]], *, explicit: bool
    ) -> bool:
        if not receipts:
            return False
        last = receipts[-1]
        argv = last.get("command") or json.loads(str(last.get("command_json") or "[]"))
        kind = command_kind([str(item) for item in argv])
        if kind == "assurance.completion-gate":
            return (
                last.get("result") == "PASSED"
                and str(last.get("semantic_state") or "") == "COMPLETE"
                and last.get("final_completion_gate_satisfied") is True
            )
        if kind == "control.completion":
            return (
                str(
                    last.get("semantic_state")
                    or last.get("parsed_result", {}).get("completion", {}).get("state")
                    or ""
                )
                == "COMPLETE"
                and last.get("final_completion_gate_satisfied") is True
            )
        return explicit and last.get("result") == "PASSED"

    def _owner_binding(self) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM campaign_owner_bindings WHERE lock_name = 'active-campaign'"
        ).fetchone()
        return None if row is None else dict(row)

    @staticmethod
    def _binding_complete(binding: dict[str, Any] | None) -> bool:
        if binding is None:
            return False
        return bool(str(binding.get("executable_identity") or "").strip()) and bool(
            str(binding.get("process_started_at_utc") or "").strip()
        )

    def _heartbeat_fresh(self, row: sqlite3.Row | dict[str, Any]) -> bool:
        last = datetime.fromisoformat(str(row["last_heartbeat_utc"]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        max_age = max(self.heartbeat_seconds * 3.0, 90.0)
        return (datetime.now(UTC) - last).total_seconds() <= max_age

    def _live_qualification_owner_blocks_recover(self, row: sqlite3.Row | dict[str, Any]) -> bool:
        """Block recover only for a distinct live child or identity-matched owner.

        A qualification lock that shares a PID with the campaign lock is not an
        owner when the live process identity does not match the stored binding.
        That is PID reuse: recover is the governed takeover.
        """

        lock = self._db.execute(
            "SELECT * FROM qualification_locks WHERE lock_name = 'active-qualification'"
        ).fetchone()
        if lock is None:
            return False
        owner_pid = int(lock["process_id"])
        if owner_pid <= 0 or owner_pid == os.getpid():
            return False
        live = inspect_process(owner_pid)
        if live is None or not self._heartbeat_fresh(row):
            return False
        campaign_lock = self._db.execute(
            "SELECT * FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
        campaign_pid = 0 if campaign_lock is None else int(campaign_lock["process_id"])
        if campaign_pid > 0 and owner_pid != campaign_pid:
            return True
        binding = self._owner_binding()
        if not self._binding_complete(binding):
            return False
        bound = {
            "process_id": owner_pid,
            "executable": None if binding is None else binding.get("executable_identity"),
            "started_at_utc": None if binding is None else binding.get("process_started_at_utc"),
        }
        return identities_match(bound, live)

    def _upsert_owner_binding(
        self,
        campaign_id: str,
        owner: dict[str, Any],
        row: sqlite3.Row | dict[str, Any],
        now: datetime,
        *,
        reason: str,
    ) -> None:
        if not reason:
            raise ValueError("owner binding reason is required")
        payload = dict(row)
        self._db.execute(
            """
            INSERT INTO campaign_locks (lock_name, campaign_id, process_id, fence, acquired_at_utc)
            VALUES ('active-campaign', ?, ?, ?, ?)
            ON CONFLICT(lock_name) DO UPDATE SET
                campaign_id = excluded.campaign_id,
                process_id = excluded.process_id,
                fence = excluded.fence,
                acquired_at_utc = excluded.acquired_at_utc
            """,
            (
                campaign_id,
                int(owner["process_id"]),
                str(payload["fence"]),
                now.isoformat(),
            ),
        )
        self._db.execute(
            """
            INSERT INTO campaign_owner_bindings (
                lock_name, campaign_id, qualification_run_id, fence, lease_id, process_id,
                executable_identity, process_started_at_utc, service_identity, claimed_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lock_name) DO UPDATE SET
                campaign_id = excluded.campaign_id,
                qualification_run_id = excluded.qualification_run_id,
                fence = excluded.fence,
                lease_id = excluded.lease_id,
                process_id = excluded.process_id,
                executable_identity = excluded.executable_identity,
                process_started_at_utc = excluded.process_started_at_utc,
                service_identity = excluded.service_identity,
                claimed_at_utc = excluded.claimed_at_utc
            """,
            (
                "active-campaign",
                campaign_id,
                payload.get("qualification_run_id"),
                str(payload["fence"]),
                str(payload["lease_id"]),
                int(owner["process_id"]),
                str(owner.get("executable") or ""),
                str(owner.get("started_at_utc") or now.isoformat()),
                owner.get("service_identity") or payload.get("service_identity"),
                now.isoformat(),
            ),
        )

    def _assert_live_ownership(
        self, row: sqlite3.Row | dict[str, Any], *, require_current_process: bool
    ) -> None:
        lock = self._db.execute(
            "SELECT * FROM campaign_locks WHERE lock_name = 'active-campaign'"
        ).fetchone()
        if lock is None:
            raise ValueError("campaign lock is missing; recover is required")
        if str(lock["campaign_id"]) != str(row["campaign_id"]) or str(lock["fence"]) != str(
            row["fence"]
        ):
            self._disqualify(str(row["campaign_id"]), "split-brain-lock")
            raise ValueError("campaign lock does not match the campaign fence")
        binding = self._owner_binding()
        bound = {
            "process_id": lock["process_id"],
            "executable": None if binding is None else binding.get("executable_identity"),
            "started_at_utc": None if binding is None else binding.get("process_started_at_utc"),
        }
        current = current_process_identity(service_identity=dict(row).get("service_identity"))
        if not self._binding_complete(binding):
            raise ValueError("stale campaign owner requires recover")
        if int(lock["process_id"]) == os.getpid():
            if not identities_match(bound, current):
                raise ValueError("stale campaign owner requires recover")
            return
        live = inspect_process(int(lock["process_id"]))
        if live is None:
            raise ValueError("stale campaign owner requires recover")
        if identities_match(bound, live) and require_current_process:
            raise ValueError("second runner cannot mutate under the first runner fence")
        if require_current_process:
            raise ValueError("stale campaign owner requires recover")

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
