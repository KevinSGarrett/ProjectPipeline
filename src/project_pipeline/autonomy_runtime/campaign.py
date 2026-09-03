from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from project_pipeline.autonomy_runtime.admitted_release import (
    admitted_inventory_digest,
    admitted_inventory_path,
    load_admitted_release_inventory,
    write_admitted_release_inventory,
)
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
    DURATION_SECONDS,
    H4,
    H24,
    H72,
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
    "candidate_checkout_integrity",
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
# Probes that dispatch to a third-party service inherit its transient failure
# modes. A required probe must still ultimately PASS, but one transport-level
# fault must not break an otherwise healthy multi-day window.
_EXTERNAL_DEPENDENCY_PROBE_RETRY_BUDGET = 2
# Retrying a third-party fault immediately re-enters the same fault. An unspaced
# budget is spent inside a few seconds, so any transient lasting longer than the
# burst still disqualifies the window that the budget exists to protect. Attempt
# N waits _PROBE_RETRY_BACKOFF_SECONDS * 2**(N-1), bounded so the spacing can
# never approach the stale-owner boundary.
_PROBE_RETRY_BACKOFF_SECONDS = 15.0
_PROBE_RETRY_BACKOFF_MAXIMUM_SECONDS = 30.0


def _probe_retry_backoff_seconds(attempt: int) -> float:
    """Return the delay to observe before probe attempt ``attempt + 1``."""

    if attempt < 0:
        return 0.0
    return min(
        _PROBE_RETRY_BACKOFF_SECONDS * float(2**attempt),
        _PROBE_RETRY_BACKOFF_MAXIMUM_SECONDS,
    )


def _require_external_campaign_runtime_path(
    repository_root: Path, path: Path, *, label: str
) -> Path:
    """Reject mutable campaign state and evidence below a frozen candidate."""

    resolved = path.resolve()
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be outside the immutable candidate checkout")


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
    if status not in {
        "RUNNING",
        "ATTESTED",
        "72H_ATTESTED",
        "READY_TO_PUBLISH",
        "PUBLISHING",
        "PUBLISHED",
        "POST_RELEASE_VERIFYING",
        "RECONCILING",
        "COMPLETION_GATE",
    }:
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

    lock_identity_observed = bool(
        campaign_lock_live
        and str(campaign_lock_live.get("executable") or "").strip()
        and str(campaign_lock_live.get("started_at_utc") or "").strip()
    )
    if (
        lock_live
        and lock_identity_observed
        and (binding_complete or (pid_identity or {}).get("executable"))
    ):
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


def verify_campaign_publication_eligibility(
    database: Path, *, repository_root: Path, campaign_id: str
) -> dict[str, Any]:
    """Bind release publication to the recorded, attested 72-hour campaign.

    This is deliberately a read-only check so a release publisher cannot promote
    a draft by supplying a caller-controlled boolean.  The final qualification
    run, campaign state, event history, and immutable candidate identity must
    all agree before a remote finalize operation is even planned.
    """

    database = database.resolve()
    if not database.is_file():
        raise ValueError("campaign publication requires an existing campaign database")
    uri = f"file:{database.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        campaign = connection.execute(
            "SELECT * FROM campaign_runs WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        if campaign is None:
            raise ValueError("campaign publication requires a known campaign")
        if str(campaign["stage"]) != "RELEASE" or str(campaign["status"]) not in {
            "READY_TO_PUBLISH",
            "READY_TO_FINALIZE",
        }:
            raise ValueError("campaign publication requires an attested 72-hour campaign")
        run_id = str(campaign["qualification_run_id"] or "")
        qualification = connection.execute(
            """
            SELECT stage, status, attested_elapsed_seconds, window_broken, last_event_sha256
            FROM qualification_runs WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if (
            qualification is None
            or str(qualification["stage"]) != "UNATTENDED_72_HOUR"
            or str(qualification["status"]) != "ATTESTED"
            or int(qualification["window_broken"] or 0) != 0
            or not str(qualification["last_event_sha256"] or "")
            or float(qualification["attested_elapsed_seconds"] or 0) < H72.total_seconds()
        ):
            raise ValueError("campaign publication requires a completed 72-hour qualification")
        actions = {
            str(item["action"])
            for item in connection.execute(
                "SELECT action FROM campaign_events WHERE campaign_id = ?", (campaign_id,)
            ).fetchall()
        }
        required_events = {"72H_ATTESTED", "READY_TO_PUBLISH"}
        if not required_events.issubset(actions):
            raise ValueError("campaign publication evidence is incomplete")
        qualification_events = connection.execute(
            """
            SELECT action, status, payload_json, prev_event_sha256, event_sha256, created_at_utc
            FROM qualification_events
            WHERE run_id = ? ORDER BY rowid
            """,
            (run_id,),
        ).fetchall()
        previous: str | None = None
        for event in qualification_events:
            if event["prev_event_sha256"] != previous or not event["event_sha256"]:
                raise ValueError("campaign qualification event chain is incomplete")
            try:
                payload = json.loads(str(event["payload_json"]))
            except json.JSONDecodeError as exc:
                raise ValueError("campaign qualification event payload is malformed") from exc
            if not isinstance(payload, dict):
                raise ValueError("campaign qualification event payload is malformed")
            body = {
                "run_id": run_id,
                "action": str(event["action"]),
                "status": str(event["status"]),
                "payload": payload,
                "prev_event_sha256": previous,
                "created_at_utc": str(event["created_at_utc"]),
            }
            computed = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            if computed != str(event["event_sha256"]):
                raise ValueError("campaign qualification event digest is invalid")
            previous = computed
        if previous != str(qualification["last_event_sha256"]):
            raise ValueError("campaign qualification event chain is incomplete")
        campaign_events = connection.execute(
            """
            SELECT action, status, payload_json, prev_event_sha256, event_sha256, created_at_utc
            FROM campaign_events
            WHERE campaign_id = ? ORDER BY rowid
            """,
            (campaign_id,),
        ).fetchall()
        previous_campaign: str | None = None
        for event in campaign_events:
            if event["prev_event_sha256"] != previous_campaign or not event["event_sha256"]:
                raise ValueError("campaign event chain is incomplete")
            try:
                campaign_payload = json.loads(str(event["payload_json"]))
            except json.JSONDecodeError as exc:
                raise ValueError("campaign event payload is malformed") from exc
            if not isinstance(campaign_payload, dict):
                raise ValueError("campaign event payload is malformed")
            campaign_body = {
                "campaign_id": campaign_id,
                "action": str(event["action"]),
                "status": str(event["status"]),
                "payload": campaign_payload,
                "prev_event_sha256": previous_campaign,
                "created_at_utc": str(event["created_at_utc"]),
            }
            computed_campaign = hashlib.sha256(
                json.dumps(campaign_body, sort_keys=True).encode()
            ).hexdigest()
            if computed_campaign != str(event["event_sha256"]):
                raise ValueError("campaign event digest is invalid")
            previous_campaign = computed_campaign
        if previous_campaign != str(campaign["last_event_sha256"] or ""):
            raise ValueError("campaign event chain is incomplete")
        attested_inventory = None
        for item in connection.execute(
            """
            SELECT payload_json FROM campaign_events
            WHERE campaign_id = ? AND action IN ('ADMIT_4H', 'READY_TO_PUBLISH')
            ORDER BY rowid
            """,
            (campaign_id,),
        ):
            try:
                payload = json.loads(str(item["payload_json"]))
            except json.JSONDecodeError as exc:
                raise ValueError("campaign event payload is malformed") from exc
            digest = str(payload.get("admitted_inventory_sha256") or "")
            if len(digest) == 64:
                attested_inventory = digest
        if attested_inventory is None:
            raise ValueError("admitted release inventory was not attested")
        current_digest = admitted_inventory_digest(Path(str(campaign["evidence_path"])))
        if attested_inventory != current_digest:
            raise ValueError("admitted release inventory digest drifted after attestation")
    finally:
        connection.close()
    identity = inspect_worktree_identity(repository_root)
    if (
        not identity.get("ok")
        or identity.get("dirty")
        or identity.get("sha") != str(campaign["integrated_sha"])
        or identity.get("tree") != str(campaign["integrated_tree"])
    ):
        raise ValueError("campaign publication candidate identity drifted")
    inventory = load_admitted_release_inventory(Path(str(campaign["evidence_path"])))
    if (
        inventory["source_sha"] != str(campaign["integrated_sha"]).lower()
        or inventory["source_tree"] != str(campaign["integrated_tree"]).lower()
        or inventory["target_commitish"] != str(campaign["integrated_sha"]).lower()
    ):
        raise ValueError("admitted release inventory is not bound to the attested campaign")
    return {
        "campaign_id": campaign_id,
        "integrated_sha": str(campaign["integrated_sha"]),
        "integrated_tree": str(campaign["integrated_tree"]),
        "qualification_run_id": run_id,
        "attested_elapsed_seconds": float(qualification["attested_elapsed_seconds"]),
        "admitted_draft_id": int(inventory["draft_id"]),
        "admitted_tag_name": str(inventory["tag_name"]),
        "admitted_assets": tuple(inventory["assets"]),
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
        duration_probe_commands: list[list[str]] | None = None,
        probe_interval_seconds: float = 900.0,
        allow_unbound_candidate_for_tests: bool = False,
        command_environment: Mapping[str, str] | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.path = _require_external_campaign_runtime_path(
            self.repository_root,
            path,
            label="campaign_database",
        )
        self.clock = clock or SystemClock()
        self.heartbeat_seconds = float(heartbeat_seconds)
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat cadence must be positive")
        if probe_interval_seconds < 0:
            raise ValueError("probe interval cannot be negative")
        self._inspect_identity = inspect_identity or inspect_worktree_identity
        self._finalize_commands = finalize_commands
        self._duration_probe_commands = duration_probe_commands
        self._allow_unbound_candidate_for_tests = allow_unbound_candidate_for_tests
        self._command_environment = (
            None
            if command_environment is None
            else {key: str(value) for key, value in command_environment.items()}
        )
        self.probe_interval_seconds = float(probe_interval_seconds)
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

    @staticmethod
    def _build_duration_probe_entry(
        probe_id: str,
        argv: list[str],
        *,
        cadence_seconds: float,
        timeout_seconds: float = 120.0,
        retry_budget: int = 0,
        required: bool = True,
    ) -> dict[str, Any]:
        return {
            "probe_id": str(probe_id),
            "argv": list(argv),
            "cadence_seconds": float(cadence_seconds),
            "timeout_seconds": float(timeout_seconds),
            "retry_budget": int(retry_budget),
            "required": bool(required),
        }

    @staticmethod
    def _required_duration_probe_surface() -> frozenset[str]:
        return frozenset(
            {
                "candidate_identity",
                "runtime_doctor",
                "repository_validate",
                "jira_validate",
                "control_evaluate",
                "control_sequence",
                "command_center_projection",
                "autonomy_director_restart",
                "desktop_artifact_health",
                "cursor_cli_provider_dispatch",
                "github_live_readback",
                "jira_live_readback",
                "campaign_persistence_integrity",
                "recovery_isolation",
            }
        )

    def _probe_surface_complete(self, plan: list[dict[str, Any]]) -> bool:
        probe_ids = {
            str(item.get("probe_id") or "") for item in plan if bool(item.get("required", True))
        }
        return self._required_duration_probe_surface().issubset(probe_ids)

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
        state_path = _require_external_campaign_runtime_path(
            self.repository_root,
            state_path,
            label="state_path",
        )
        evidence_path = _require_external_campaign_runtime_path(
            self.repository_root,
            evidence_path,
            label="evidence_path",
        )
        pp384_evidence = _require_external_campaign_runtime_path(
            self.repository_root,
            pp384_evidence,
            label="pp384_evidence",
        )
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
            "campaign_nonce": uuid4().hex,
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
        if not self._allow_unbound_candidate_for_tests:
            self._validate_candidate_admission(row)
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
                {
                    "qualification_run_id": started["run_id"],
                    **self._admitted_inventory_attestation(row),
                },
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
        probe_label = f"heartbeat:{qual_status or row['status']}"
        if str(row["stage"]) in TIMED_STAGES:
            probe_label = self._run_due_duration_probes(campaign_id, row, now, probe_label)
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), probe_label, campaign_id),
            )
            self._append_event(
                campaign_id,
                "HEARTBEAT",
                str(row["status"]),
                {"qualification_status": qual_status, "last_probe": probe_label},
                now,
            )
        return self.get(campaign_id)

    def advance(self, campaign_id: str) -> dict[str, Any]:
        row = self.get(campaign_id)
        stage = str(row["stage"])
        status = str(row["status"])
        if status in {"DISQUALIFIED", "FAILED", "STOPPED", "FINALIZED"}:
            return row
        if status == "72H_ATTESTED":
            return self._mark_ready_to_publish(campaign_id)
        if status in {"READY_TO_PUBLISH", "READY_TO_FINALIZE"}:
            return self.finalize(campaign_id)
        if status == "PUBLISHED":
            return self._post_release_verify(campaign_id)
        if status in {"POST_RELEASE_VERIFYING", "RECONCILING"}:
            return self._reconcile_release(campaign_id)
        if status == "COMPLETION_GATE":
            return self._run_completion_gate_phase(campaign_id)
        if stage == "RECOVERY" and status == "ATTESTED":
            return self.admit_4h(campaign_id)
        if stage in TIMED_STAGES and row["qualification_run_id"]:
            run_id = str(row["qualification_run_id"])
            try:
                row = self.heartbeat(campaign_id)
                if not self._duration_window_elapsed(run_id, stage):
                    return row
                self._assert_duration_completion_proof(campaign_id, row)
                attested = self.qualification.complete(run_id)
            except ValueError:
                if str(self.get(campaign_id)["status"]) == "DISQUALIFIED":
                    return self.get(campaign_id)
                # A qualification-store integrity halt during heartbeat must not
                # mask missing in-window duration proof once the stage window has
                # already elapsed. Prefer the explicit probe-missing/gap/stale
                # reasons from completion proof over a generic integrity label.
                if self._duration_window_elapsed(run_id, stage):
                    try:
                        self._assert_duration_completion_proof(campaign_id, self.get(campaign_id))
                    except ValueError:
                        if str(self.get(campaign_id)["status"]) == "DISQUALIFIED":
                            return self.get(campaign_id)
                current = self.qualification.get(run_id)
                if str(current["status"]) in {"DISQUALIFIED", "FAILED", "STOPPED"}:
                    self._disqualify(campaign_id, "qualification-completion-integrity-failed")
                    return self.get(campaign_id)
                return self.heartbeat(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_4_HOUR":
                return self.admit_24h(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_24_HOUR":
                return self.admit_72h(campaign_id)
            if attested["status"] == "ATTESTED" and stage == "UNATTENDED_72_HOUR":
                self._mark_72h_attested(campaign_id)
                return self.advance(campaign_id)
        return self.heartbeat(campaign_id)

    def recover(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        if str(row["status"]) in {"DISQUALIFIED", "FAILED", "STOPPED", "FINALIZED"}:
            raise ValueError(
                "terminal campaign cannot recover; preserve its evidence and start a "
                "fresh candidate only after corrective governance"
            )
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
            # A broken timed window invalidates its campaign.  Do not create a
            # successor under the parent credential scope: a new campaign must
            # receive a fresh governed runtime binding and credential envelope.
            return preserved
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
        timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        row = self._require(campaign_id)
        command_sha256 = hashlib.sha256(json.dumps(argv, sort_keys=True).encode()).hexdigest()
        effective_idempotency_key = idempotency_key or (
            "CIDEMP:"
            + hashlib.sha256(
                json.dumps(
                    {
                        "campaign_id": campaign_id,
                        "command_sha256": command_sha256,
                        "stage": str(row["stage"]),
                        "status": str(row["status"]),
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()[:24]
        )
        existing = self._db.execute(
            """
            SELECT * FROM campaign_command_receipts
            WHERE campaign_id = ? AND idempotency_key = ?
            ORDER BY rowid
            LIMIT 1
            """,
            (campaign_id, effective_idempotency_key),
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
            timeout_seconds=timeout_seconds,
            idempotency_key=effective_idempotency_key,
            evidence_links=evidence_links,
            expected_sha=str(row["integrated_sha"]),
            expected_tree=str(row["integrated_tree"]),
            environment_class="campaign-bound"
            if self._command_environment is not None
            else "local",
            environment=self._command_environment,
        )
        receipt["idempotency_key"] = effective_idempotency_key
        now = datetime.now(UTC)
        body = {
            "campaign_id": campaign_id,
            "command_sha256": command_sha256,
            "idempotency_key": effective_idempotency_key,
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
        if str(row["stage"]) != "RELEASE" or str(row["status"]) not in {
            "READY_TO_PUBLISH",
            "READY_TO_FINALIZE",
        }:
            raise ValueError("finalize requires an attested 72-hour campaign ready to publish")
        self._assert_live_ownership(row, require_current_process=True)
        self._assert_identity(row)
        planned = commands or self._finalize_commands or self._default_publish_commands(row)
        receipts = []
        for argv in planned:
            receipts.append(self.execute(campaign_id, argv))
        now = datetime.now(UTC)
        failed = [item for item in receipts if item.get("result") != "PASSED"]
        publication_receipts = []
        for item in receipts:
            publication = (item.get("parsed_result") or {}).get("publication")
            if (
                item.get("result_semantics") == "remote-publication-verified"
                and isinstance(publication, dict)
                and publication.get("provider") == "github-rest"
                and publication.get("fixture_desktop") is False
            ):
                publication_receipts.append(item)
        if not publication_receipts:
            failed.append(
                {
                    "receipt_id": None,
                    "result": "FAILED",
                    "result_semantics": "remote-publication-receipt-missing",
                }
            )
        if failed:
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
                        "publication_receipts": [
                            item.get("receipt_id") for item in publication_receipts
                        ],
                    },
                    now,
                )
            result = self.get(campaign_id)
            result["publication_receipts"] = receipts
            return result
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'POST_RELEASE', status = 'PUBLISHED',
                    next_transition = 'POST_RELEASE_VERIFYING',
                    last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), "publish-executed", campaign_id),
            )
            self._append_event(
                campaign_id,
                "PUBLISHED",
                "PUBLISHED",
                {"receipts": [item.get("receipt_id") for item in receipts]},
                now,
            )
        result = self.get(campaign_id)
        result["publication_receipts"] = receipts
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

    def _mark_72h_attested(self, campaign_id: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'RELEASE', status = '72H_ATTESTED',
                    next_transition = 'READY_TO_PUBLISH', last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), "72h-attested", campaign_id),
            )
            self._append_event(campaign_id, "72H_ATTESTED", "72H_ATTESTED", {}, now)
        return self.get(campaign_id)

    def _mark_ready_to_publish(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        self._require_bound_admitted_inventory(row)
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'RELEASE', status = 'READY_TO_PUBLISH',
                    next_transition = 'PUBLISHING', last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), "ready-to-publish", campaign_id),
            )
            self._append_event(campaign_id, "READY_TO_PUBLISH", "READY_TO_PUBLISH", self._admitted_inventory_attestation(row), now)
        return self.get(campaign_id)

    def _require_clean_identity(self) -> dict[str, Any]:
        identity = self._inspect_identity(self.repository_root)
        if not identity.get("ok"):
            raise ValueError("campaign cannot inspect a pinned worktree identity")
        if identity.get("dirty"):
            raise ValueError("campaign requires a clean immutable worktree")
        return identity

    def _validate_candidate_admission(self, row: sqlite3.Row | dict[str, Any]) -> None:
        """Fail closed before a timed window can accrue against an unbound candidate.

        Runtime evidence lives outside the frozen source tree, but must bind the
        immutable candidate, remote draft, remote-byte lifecycle, and concrete
        artifact manifest before the four-hour stage begins.
        """

        evidence_root = Path(str(row["evidence_path"])).resolve()
        candidate_path = evidence_root / "candidate-admission.json"
        if not candidate_path.is_file():
            raise ValueError("4-hour admission requires candidate-admission evidence")
        try:
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("candidate-admission evidence is malformed") from error
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0.0":
            raise ValueError("candidate-admission evidence has an unsupported schema")
        if payload.get("integrated_sha") != str(row["integrated_sha"]) or payload.get(
            "integrated_tree"
        ) != str(row["integrated_tree"]):
            raise ValueError("candidate-admission evidence is bound to another subject")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("candidate-admission evidence has no artifacts")
        names: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise ValueError("candidate-admission artifact is malformed")
            name = str(artifact.get("name") or "")
            digest = str(artifact.get("sha256") or "")
            path = Path(str(artifact.get("path") or ""))
            if (
                not name
                or len(digest) != 64
                or not path.is_absolute()
                or not path.is_file()
                or not path.resolve().is_relative_to(evidence_root)
            ):
                raise ValueError("candidate-admission artifact is unavailable")
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("candidate-admission artifact digest mismatch")
            names.add(name)
        if len(names) != len(artifacts):
            raise ValueError("candidate-admission artifact names are not unique")
        draft = payload.get("draft_release")
        if not isinstance(draft, dict):
            raise ValueError("candidate-admission draft release is missing")
        if (
            not isinstance(draft.get("release_id"), int)
            or draft.get("draft") is not True
            or draft.get("target_commitish") != str(row["integrated_sha"])
        ):
            raise ValueError("candidate-admission draft release is invalid")
        draft_assets = draft.get("assets")
        remote_names = (
            {
                str(asset.get("name"))
                for asset in draft_assets
                if isinstance(asset, dict) and asset.get("name")
            }
            if isinstance(draft_assets, list)
            else set()
        )
        if (
            not isinstance(draft_assets, list)
            or remote_names != names
            or len(draft_assets) != len(artifacts)
        ):
            raise ValueError("candidate-admission draft assets do not match the manifest")
        lifecycle = payload.get("remote_lifecycle")
        checks = lifecycle.get("checks") if isinstance(lifecycle, dict) else None
        if (
            not isinstance(lifecycle, dict)
            or lifecycle.get("state") != "VERIFIED"
            or lifecycle.get("source") != "REMOTE_DRAFT_BYTES"
            or lifecycle.get("worktree_bytes_used") is not False
            or lifecycle.get("execution_mode") != "REAL_NATIVE_REMOTE_BYTES"
            or not isinstance(checks, dict)
            or not checks
            or not all(str(value).startswith("PASS") for value in checks.values())
        ):
            raise ValueError("candidate-admission remote lifecycle is unverified")
        acquired_dir = Path(str(lifecycle.get("acquired_dir") or ""))
        if not acquired_dir.is_absolute() or not acquired_dir.is_relative_to(evidence_root):
            raise ValueError("candidate-admission acquired remote bytes are unavailable")
        from project_pipeline.release_factory.lifecycle import verify_acquired_assets

        try:
            verify_acquired_assets(
                acquired_dir,
                expected_sha256s={str(item["name"]): str(item["sha256"]) for item in artifacts},
            )
        except (OSError, ValueError) as error:
            raise ValueError("candidate-admission acquired remote bytes are unverified") from error
        from project_pipeline.autonomy_runtime.duration_probes import verify_remote_candidate

        remote = verify_remote_candidate(
            self.repository_root,
            {"identity_ok": True, "payload": payload},
            expected_sha=str(row["integrated_sha"]),
        )
        if remote.get("ok") is not True:
            raise ValueError("candidate-admission live remote draft verification failed")
        self._bind_admitted_inventory_from_admission(evidence_root, payload, row)

    def _bind_admitted_inventory_from_admission(
        self,
        evidence_root: Path,
        payload: dict[str, Any],
        row: sqlite3.Row | dict[str, Any],
    ) -> None:
        draft = payload["draft_release"]
        artifacts = payload["artifacts"]
        tag_name = str(draft.get("tag_name") or payload.get("tag_name") or "")
        if not tag_name:
            raise ValueError("candidate-admission draft tag is missing")
        assets: list[dict[str, Any]] = []
        by_name = {
            str(item.get("name")): item for item in draft.get("assets") or [] if isinstance(item, dict)
        }
        for artifact in artifacts:
            name = str(artifact["name"])
            remote_asset = by_name.get(name) or {}
            path = Path(str(artifact["path"]))
            try:
                asset_id = int(remote_asset.get("id") or remote_asset.get("api_id"))
            except (TypeError, ValueError) as error:
                raise ValueError("candidate-admission draft asset identity is incomplete") from error
            assets.append(
                {
                    "id": asset_id,
                    "name": name,
                    "sha256": str(artifact["sha256"]),
                    "size_bytes": int(path.stat().st_size),
                }
            )
        write_admitted_release_inventory(
            evidence_root,
            {
                "draft_id": int(draft["release_id"]),
                "tag_name": tag_name,
                "target_commitish": str(row["integrated_sha"]),
                "source_sha": str(row["integrated_sha"]),
                "source_tree": str(row["integrated_tree"]),
                "assets": assets,
            },
        )

    def _admitted_inventory_attestation(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        evidence = Path(str(row["evidence_path"]))
        if not admitted_inventory_path(evidence).is_file():
            if self._allow_unbound_candidate_for_tests:
                return {}
            raise ValueError("campaign requires an admitted release inventory")
        return {"admitted_inventory_sha256": admitted_inventory_digest(evidence)}

    def _attested_inventory_digest(self, campaign_id: str) -> str | None:
        rows = self._db.execute(
            """
            SELECT payload_json FROM campaign_events
            WHERE campaign_id = ? AND action IN ('ADMIT_4H', 'READY_TO_PUBLISH')
            ORDER BY rowid
            """,
            (campaign_id,),
        ).fetchall()
        attested: str | None = None
        for item in rows:
            try:
                payload = json.loads(str(item["payload_json"]))
            except json.JSONDecodeError:
                continue
            digest = str(payload.get("admitted_inventory_sha256") or "")
            if len(digest) == 64:
                attested = digest
        return attested

    def _require_bound_admitted_inventory(self, row: sqlite3.Row | dict[str, Any]) -> None:
        inventory = load_admitted_release_inventory(Path(str(row["evidence_path"])))
        if (
            inventory["source_sha"] != str(row["integrated_sha"]).lower()
            or inventory["source_tree"] != str(row["integrated_tree"]).lower()
            or inventory["target_commitish"] != str(row["integrated_sha"]).lower()
        ):
            raise ValueError("admitted release inventory is not bound to the attested campaign")
        digest = admitted_inventory_digest(Path(str(row["evidence_path"])))
        attested = self._attested_inventory_digest(str(row["campaign_id"]))
        if attested is None:
            raise ValueError("admitted release inventory was not attested")
        if attested != digest:
            raise ValueError("admitted release inventory digest drifted after attestation")

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

    def _default_duration_probes(self) -> list[list[str]]:
        return [item["argv"] for item in self._default_duration_probe_plan()]

    def _default_duration_probe_plan(
        self, row: sqlite3.Row | dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        python = self._python()
        root = str(self.repository_root)
        cadence = max(0.0, self.probe_interval_seconds)
        source = dict(row) if row is not None else {}
        expected_sha = str(source.get("integrated_sha") or "")
        expected_tree = str(source.get("integrated_tree") or "")
        campaign_id = str(source.get("campaign_id") or "")
        if row is None:
            unbound_root = self.path.parent / f"duration-probe-plan-{uuid4().hex}"
            evidence_root = unbound_root / "evidence"
            state_root = unbound_root / "state"
        else:
            raw_evidence_root = str(source.get("evidence_path") or "").strip()
            raw_state_root = str(source.get("state_path") or "").strip()
            if not raw_evidence_root or not raw_state_root:
                raise ValueError(
                    "bound duration probe plan requires external evidence and state roots"
                )
            evidence_root = Path(raw_evidence_root)
            state_root = Path(raw_state_root)
        evidence_root = _require_external_campaign_runtime_path(
            self.repository_root,
            evidence_root,
            label="evidence_path",
        )
        state_root = _require_external_campaign_runtime_path(
            self.repository_root,
            state_root,
            label="state_path",
        )
        # The live Cursor qualification is intentionally bounded but can take longer
        # than a local health probe.  Keep its allowance below the stale-owner
        # boundary while scaling it with the heartbeat used by the running campaign.
        cursor_timeout = min(120.0, max(60.0, self.heartbeat_seconds * 2.0))

        def duration_probe(
            probe_id: str,
            *,
            cadence_seconds: float = cadence,
            timeout_seconds: float = 75.0,
            retry_budget: int = 0,
        ) -> dict[str, Any]:
            return self._build_duration_probe_entry(
                probe_id,
                [
                    python,
                    str(self.repository_root / "scripts" / "campaign_duration_probe.py"),
                    "--probe-id",
                    probe_id,
                    "--repository-root",
                    root,
                    "--expected-sha",
                    expected_sha,
                    "--expected-tree",
                    expected_tree,
                    "--campaign-database",
                    str(self.path),
                    "--campaign-id",
                    campaign_id,
                    "--candidate-evidence",
                    str(evidence_root / "candidate-admission.json"),
                    "--state-root",
                    str(state_root / "duration-probes"),
                ],
                cadence_seconds=cadence_seconds,
                timeout_seconds=timeout_seconds,
                retry_budget=retry_budget,
                required=True,
            )

        return [
            duration_probe("candidate_identity", timeout_seconds=30.0),
            self._build_duration_probe_entry(
                "runtime_doctor",
                [python, "-m", "project_pipeline", "doctor", "--root", root],
                cadence_seconds=cadence,
                timeout_seconds=60.0,
                retry_budget=0,
                required=True,
            ),
            self._build_duration_probe_entry(
                "repository_validate",
                [python, "-m", "project_pipeline", "validate", "--root", root],
                cadence_seconds=cadence,
                timeout_seconds=60.0,
                retry_budget=0,
                required=True,
            ),
            self._build_duration_probe_entry(
                "jira_validate",
                [python, "-m", "project_pipeline", "jira", "validate", "--root", root],
                cadence_seconds=cadence,
                timeout_seconds=60.0,
                retry_budget=0,
                required=True,
            ),
            self._build_duration_probe_entry(
                "control_evaluate",
                [python, "-m", "project_pipeline", "control", "evaluate", "--root", root],
                cadence_seconds=cadence,
                timeout_seconds=60.0,
                retry_budget=0,
                required=True,
            ),
            self._build_duration_probe_entry(
                "control_sequence",
                [python, "-m", "project_pipeline", "control", "sequence", "--root", root],
                cadence_seconds=cadence,
                timeout_seconds=60.0,
                retry_budget=0,
                required=True,
            ),
            duration_probe("command_center_projection", timeout_seconds=60.0),
            duration_probe("autonomy_director_restart", timeout_seconds=60.0),
            duration_probe("desktop_artifact_health", timeout_seconds=45.0),
            duration_probe(
                "cursor_cli_provider_dispatch",
                cadence_seconds=max(cadence, 4 * 60 * 60),
                timeout_seconds=cursor_timeout,
                retry_budget=_EXTERNAL_DEPENDENCY_PROBE_RETRY_BUDGET,
            ),
            duration_probe(
                "github_live_readback",
                timeout_seconds=45.0,
                retry_budget=_EXTERNAL_DEPENDENCY_PROBE_RETRY_BUDGET,
            ),
            duration_probe(
                "jira_live_readback",
                timeout_seconds=45.0,
                retry_budget=_EXTERNAL_DEPENDENCY_PROBE_RETRY_BUDGET,
            ),
            duration_probe("campaign_persistence_integrity", timeout_seconds=30.0),
            duration_probe("recovery_isolation", timeout_seconds=30.0),
        ]

    def _duration_probe_plan(
        self, row: sqlite3.Row | dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        commands = self._duration_probe_commands
        if commands is None:
            return self._default_duration_probe_plan(row)
        cadence = max(0.0, self.probe_interval_seconds)
        plan: list[dict[str, Any]] = []
        for idx, argv in enumerate(commands):
            plan.append(
                self._build_duration_probe_entry(
                    f"custom_probe_{idx + 1}",
                    argv,
                    cadence_seconds=cadence,
                    timeout_seconds=60.0,
                    retry_budget=0,
                    required=True,
                )
            )
        return plan

    def _last_duration_probe_at(self, campaign_id: str, probe_id: str) -> datetime | None:
        rows = self._db.execute(
            """
            SELECT created_at_utc, payload_json FROM campaign_events
            WHERE campaign_id = ? AND action = 'PROBE'
            ORDER BY rowid DESC
            """,
            (campaign_id,),
        ).fetchall()
        for event in rows:
            try:
                payload = json.loads(str(event["payload_json"]))
            except json.JSONDecodeError:
                continue
            probes = payload.get("probes") if isinstance(payload, dict) else None
            if not isinstance(probes, list):
                continue
            if not any(
                isinstance(item, dict) and item.get("probe_id") == probe_id for item in probes
            ):
                continue
            stamp = datetime.fromisoformat(str(event["created_at_utc"]))
            return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp
        return None

    def _mark_duration_probe_running(
        self,
        campaign_id: str,
        row: sqlite3.Row | dict[str, Any],
        probe_id: str,
        attempt: int,
    ) -> None:
        """Keep recovery telemetry fresh while one bounded probe owns the runner.

        A duration probe executes synchronously, so its maximum runtime must stay
        below the stale-owner boundary. Recording immediately before every
        attempt makes recovery distinguish a live, bounded probe from a stalled
        runner without inventing a second writer for the campaign database.
        """

        run_id = str(row["qualification_run_id"] or "")
        if run_id:
            qualification = self.qualification.get(run_id)
            if str(qualification["status"]) not in ACTIVE:
                self._disqualify(campaign_id, "duration-probe-qualification-not-active")
                raise ValueError("duration probe requires an active qualification run")
            try:
                self.qualification.heartbeat(run_id, fence=str(qualification["fence"]))
            except ValueError:
                self._disqualify(campaign_id, "duration-probe-qualification-heartbeat-failed")
                raise
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    f"probe-running:{probe_id}:attempt-{attempt + 1}",
                    campaign_id,
                ),
            )

    def _run_due_duration_probes(
        self,
        campaign_id: str,
        row: sqlite3.Row | dict[str, Any],
        now: datetime,
        fallback_label: str,
    ) -> str:
        plan = self._duration_probe_plan(row)
        if self._duration_probe_commands is None and not self._probe_surface_complete(plan):
            self._disqualify(campaign_id, "duration-probe-surface-incomplete")
            raise ValueError("duration probe surface incomplete")
        receipt_ids: list[str] = []
        probe_results: list[dict[str, Any]] = []
        for item in plan:
            probe_id = str(item.get("probe_id") or "probe")
            cadence_seconds = float(item.get("cadence_seconds", self.probe_interval_seconds))
            last_probe = self._last_duration_probe_at(campaign_id, probe_id)
            if last_probe is not None and (now - last_probe).total_seconds() < cadence_seconds:
                continue
            argv = [str(token) for token in item.get("argv", [])]
            timeout_seconds = float(item.get("timeout_seconds", 120.0))
            retries = max(0, int(item.get("retry_budget", 0)))
            required = bool(item.get("required", True))
            stale_owner_boundary = max(self.heartbeat_seconds * 3.0, 90.0)
            if timeout_seconds >= stale_owner_boundary:
                self._disqualify(campaign_id, "duration-probe-timeout-exceeds-heartbeat-window")
                raise ValueError("duration probe timeout exceeds heartbeat window")
            attempt = 0
            receipt: dict[str, Any] | None = None
            superseded_receipt_ids: list[str] = []
            while attempt <= retries:
                self._mark_duration_probe_running(campaign_id, row, probe_id, attempt)
                receipt = self.execute(
                    campaign_id,
                    argv,
                    timeout_seconds=timeout_seconds,
                    idempotency_key=(
                        f"CIDEMP:{campaign_id}:{probe_id}:{(last_probe or now).isoformat()}:{attempt}"
                    ),
                    evidence_links=[
                        f"probe:{probe_id}",
                        f"attempt:{attempt + 1}",
                        f"required:{str(required).lower()}",
                    ],
                )
                if receipt.get("result") == "PASSED":
                    break
                if attempt < retries:
                    superseded_receipt_ids.append(str(receipt["receipt_id"]))
                    backoff = _probe_retry_backoff_seconds(attempt)
                    if backoff > 0.0:
                        # The probe still owns the runner while it waits, so
                        # liveness is refreshed through the same primitive the
                        # attempts use. Calling heartbeat() here would re-enter
                        # this function, because heartbeat() is what runs probes.
                        self._mark_duration_probe_running(campaign_id, row, probe_id, attempt)
                        time.sleep(backoff)
                attempt += 1
            if receipt is None:
                continue
            receipt_ids.append(str(receipt["receipt_id"]))
            probe_results.append(
                {
                    "probe_id": probe_id,
                    "required": required,
                    "result": receipt.get("result"),
                    "receipt_id": receipt.get("receipt_id"),
                    "result_semantics": receipt.get("result_semantics"),
                    "semantic_state": receipt.get("semantic_state"),
                    "attempts": len(superseded_receipt_ids) + 1,
                    "superseded_receipt_ids": list(superseded_receipt_ids),
                    "final_completion_gate_satisfied": bool(
                        receipt.get("final_completion_gate_satisfied")
                    ),
                }
            )
            event_now = datetime.now(UTC)
            with self._db:
                self._append_event(
                    campaign_id,
                    "PROBE",
                    str(row["status"]),
                    {
                        "receipt_ids": [str(receipt["receipt_id"])],
                        "last_probe": f"probe:{receipt['receipt_id']}",
                        "probes": [probe_results[-1]],
                    },
                    event_now,
                )
            if required and receipt.get("result") != "PASSED":
                self._disqualify(campaign_id, "duration-probe-failed")
                raise ValueError(f"duration probe failed: {probe_id}")
        label = "probe:" + ",".join(receipt_ids)
        return label

    @staticmethod
    def _probe_retry_allowance(plan: list[dict[str, Any]]) -> float:
        """Return the worst-case extra wall time one probe cycle may spend retrying.

        Probes run serially, so a retried probe delays every later probe in the
        same cycle. Staleness must be measured against the retry allowance the
        plan actually grants, otherwise tolerating a transient fault in one probe
        would report stale evidence for an unrelated healthy probe.

        The whole-plan sum is deliberately conservative: a probe early in the
        cycle inherits the allowance of probes ordered after it. Liveness is
        already enforced per attempt by the timeout and the heartbeat, so this
        backstop is better slightly loose than prone to false staleness.
        """

        allowance = 0.0
        for item in plan:
            retries = max(0, int(item.get("retry_budget", 0)))
            allowance += retries * float(item.get("timeout_seconds", 120.0))
            # Spacing between attempts is wall time the plan grants just as
            # deliberately as the attempts themselves.
            allowance += sum(_probe_retry_backoff_seconds(index) for index in range(retries))
        return allowance

    def _duration_window_elapsed(self, run_id: str, stage: str) -> bool:
        """Report whether the timed run has already served its full stage duration.

        Completion proof is a claim that the window finished, so it may only be
        evaluated once the window could actually be finished. A stage that has
        just been admitted has no probe evidence inside its own window yet, and
        treating that as missing evidence would terminally disqualify a healthy
        campaign one heartbeat after a successful stage transition.
        """

        required = DURATION_SECONDS.get(stage)
        if required is None:
            return True
        run = self.qualification.get(run_id)
        started = datetime.fromisoformat(str(run["started_at_utc"]))
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return (datetime.now(UTC) - started).total_seconds() >= required

    def _assert_duration_completion_proof(
        self, campaign_id: str, row: sqlite3.Row | dict[str, Any]
    ) -> None:
        """Require contiguous successful, identity-bound probe evidence before attestation."""

        run_id = str(row["qualification_run_id"] or "")
        qualification = self.qualification.get(run_id)
        started = datetime.fromisoformat(str(qualification["started_at_utc"]))
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        plan = self._duration_probe_plan(row)
        required = {
            str(item.get("probe_id") or "") for item in plan if bool(item.get("required", True))
        }
        if not required or (
            self._duration_probe_commands is None and not self._probe_surface_complete(plan)
        ):
            self._disqualify(campaign_id, "duration-completion-probe-surface-incomplete")
            raise ValueError("duration completion requires the complete probe surface")
        receipt_rows = self._db.execute(
            """
            SELECT receipt_id, result, evidence_json FROM campaign_command_receipts
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchall()
        receipts = {str(item["receipt_id"]): item for item in receipt_rows}
        observations: dict[str, list[datetime]] = {probe_id: [] for probe_id in required}
        events = self._db.execute(
            """
            SELECT created_at_utc, payload_json FROM campaign_events
            WHERE campaign_id = ? AND action = 'PROBE' ORDER BY rowid
            """,
            (campaign_id,),
        ).fetchall()
        for event in events:
            stamp = datetime.fromisoformat(str(event["created_at_utc"]))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            if stamp < started:
                continue
            try:
                payload = json.loads(str(event["payload_json"]))
            except json.JSONDecodeError:
                continue
            probes = payload.get("probes") if isinstance(payload, dict) else None
            if not isinstance(probes, list):
                continue
            for probe in probes:
                if not isinstance(probe, dict):
                    continue
                probe_id = str(probe.get("probe_id") or "")
                receipt_id = str(probe.get("receipt_id") or "")
                receipt = receipts.get(receipt_id)
                if (
                    probe_id not in required
                    or probe.get("result") != "PASSED"
                    or receipt is None
                    or str(receipt["result"]) != "PASSED"
                ):
                    continue
                try:
                    evidence = json.loads(str(receipt["evidence_json"]))
                except json.JSONDecodeError:
                    continue
                if evidence.get("integrated_sha") != str(row["integrated_sha"]) or evidence.get(
                    "integrated_tree"
                ) != str(row["integrated_tree"]):
                    continue
                observations[probe_id].append(stamp)
        now = datetime.now(UTC)
        grace_seconds = max(self.heartbeat_seconds * 3.0, 90.0) + self._probe_retry_allowance(plan)
        for item in plan:
            probe_id = str(item.get("probe_id") or "")
            if probe_id not in required:
                continue
            stamps = observations[probe_id]
            max_gap = (
                float(item.get("cadence_seconds", self.probe_interval_seconds)) + grace_seconds
            )
            previous = started
            if not stamps:
                self._disqualify(campaign_id, f"duration-completion-probe-missing:{probe_id}")
                raise ValueError(f"duration completion probe evidence is missing: {probe_id}")
            for stamp in stamps:
                if (stamp - previous).total_seconds() > max_gap:
                    self._disqualify(campaign_id, f"duration-completion-probe-gap:{probe_id}")
                    raise ValueError(f"duration completion probe evidence is stale: {probe_id}")
                previous = stamp
            if (now - previous).total_seconds() > max_gap:
                self._disqualify(campaign_id, f"duration-completion-probe-stale:{probe_id}")
                raise ValueError(f"duration completion probe evidence is stale: {probe_id}")

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
        release_identity = (
            row.get("release_identity")
            if isinstance(row, dict)
            else (None if row is None else row["release_identity"])
        )
        identity = str(release_identity) if release_identity else "REL-local"
        archive = evidence / f"{identity}.zip"
        return [
            [python, "-m", "project_pipeline", "archive", "--root", root, "--output", str(archive)],
            [python, "-m", "project_pipeline", "verify-archive", "--archive", str(archive)],
            [python, "-m", "project_pipeline", "security", "sbom", "--root", root],
            [python, "-m", "project_pipeline", "security", "supply-chain", "--root", root],
            [python, "-m", "project_pipeline", "resilience", "status", "--root", root],
            [python, "-m", "project_pipeline", "validate", "--root", root],
            [python, "-m", "project_pipeline", "jira", "validate", "--root", root],
        ]

    def _default_publish_commands(
        self, row: sqlite3.Row | dict[str, Any] | None = None
    ) -> list[list[str]]:
        if row is None:
            raise ValueError("campaign publication requires the bound campaign row")
        evidence = Path(str(row["evidence_path"]))
        desktop_dir = evidence / "desktop-artifacts"
        return [
            *self._default_finalize_commands(row),
            [
                self._python(),
                str(self.repository_root / "scripts" / "campaign_release_publication.py"),
                "--repository-root",
                str(self.repository_root),
                "--campaign-database",
                str(self.path),
                "--campaign-id",
                str(row["campaign_id"]),
                "--evidence-path",
                str(evidence),
                "--desktop-dir",
                str(desktop_dir),
            ],
        ]

    def _default_post_release_commands(
        self, row: sqlite3.Row | dict[str, Any] | None = None
    ) -> list[list[str]]:
        if row is None:
            raise ValueError("post-release verification requires the bound campaign row")
        evidence = Path(str(row["evidence_path"]))
        acquired_dir = (
            evidence
            / "remote-acquired"
            / (
                f"candidate-{str(row['integrated_sha']).lower()}-{str(row['integrated_tree']).lower()}"
            )
        )
        lifecycle_work_dir = acquired_dir.parent / f"lifecycle-{acquired_dir.name}"
        return [
            [
                self._python(),
                str(self.repository_root / "scripts" / "verify_campaign_post_release.py"),
                "--repository-root",
                str(self.repository_root),
                "--acquired-dir",
                str(acquired_dir),
                "--work-dir",
                str(lifecycle_work_dir),
                "--expected-sha",
                str(row["integrated_sha"]),
                "--expected-tree",
                str(row["integrated_tree"]),
            ],
            [self._python(), str(self.repository_root / "scripts" / "campaign_probe.py")],
        ]

    def _default_reconcile_commands(self) -> list[list[str]]:
        python = self._python()
        root = str(self.repository_root)
        return [
            [python, "-m", "project_pipeline", "control", "completion", "--root", root],
            [python, "-m", "project_pipeline", "jira", "validate", "--root", root],
        ]

    def _default_completion_gate_commands(self) -> list[list[str]]:
        python = self._python()
        root = str(self.repository_root)
        return [[python, "-m", "project_pipeline", "assurance", "completion-gate", "--root", root]]

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

    def _post_release_verify(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        if str(row["status"]) != "PUBLISHED":
            raise ValueError("post-release verification requires PUBLISHED state")
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET status = 'POST_RELEASE_VERIFYING', last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (datetime.now(UTC).isoformat(), "post-release-verify-started", campaign_id),
            )
        receipts: list[dict[str, Any]] = []
        for argv in self._default_post_release_commands(row):
            receipts.append(self.execute(campaign_id, argv))
        now = datetime.now(UTC)
        if any(item.get("result") != "PASSED" for item in receipts):
            with self._db:
                self._db.execute(
                    "UPDATE campaign_runs SET status = 'FAILED', last_heartbeat_utc = ?, last_probe = ? WHERE campaign_id = ?",
                    (now.isoformat(), "post-release-verify-failed", campaign_id),
                )
                self._append_event(
                    campaign_id,
                    "POST_RELEASE_VERIFY_FAILED",
                    "FAILED",
                    {"receipts": [item.get("receipt_id") for item in receipts]},
                    now,
                )
            result = self.get(campaign_id)
            result["post_release_receipts"] = receipts
            return result
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET status = 'RECONCILING', next_transition = 'COMPLETION_GATE',
                    last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), "post-release-verified", campaign_id),
            )
            self._append_event(
                campaign_id,
                "POST_RELEASE_VERIFIED",
                "RECONCILING",
                {"receipts": [item.get("receipt_id") for item in receipts]},
                now,
            )
        result = self.get(campaign_id)
        result["post_release_receipts"] = receipts
        return result

    def _reconcile_release(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        if str(row["status"]) not in {"POST_RELEASE_VERIFYING", "RECONCILING"}:
            raise ValueError("reconciliation requires POST_RELEASE_VERIFYING/RECONCILING state")
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET status = 'RECONCILING', last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (datetime.now(UTC).isoformat(), "reconcile-started", campaign_id),
            )
        receipts: list[dict[str, Any]] = []
        for argv in self._default_reconcile_commands():
            receipts.append(self.execute(campaign_id, argv))
        now = datetime.now(UTC)
        if any(item.get("result") != "PASSED" for item in receipts):
            with self._db:
                self._db.execute(
                    "UPDATE campaign_runs SET status = 'FAILED', last_heartbeat_utc = ?, last_probe = ? WHERE campaign_id = ?",
                    (now.isoformat(), "reconcile-failed", campaign_id),
                )
                self._append_event(
                    campaign_id,
                    "RECONCILE_FAILED",
                    "FAILED",
                    {"receipts": [item.get("receipt_id") for item in receipts]},
                    now,
                )
            result = self.get(campaign_id)
            result["reconcile_receipts"] = receipts
            return result
        with self._db:
            self._db.execute(
                """
                UPDATE campaign_runs
                SET stage = 'COMPLETION_GATE', status = 'COMPLETION_GATE', next_transition = 'FINALIZED',
                    last_heartbeat_utc = ?, last_probe = ?
                WHERE campaign_id = ?
                """,
                (now.isoformat(), "reconciled", campaign_id),
            )
            self._append_event(
                campaign_id,
                "RECONCILED",
                "COMPLETION_GATE",
                {"receipts": [item.get("receipt_id") for item in receipts]},
                now,
            )
        result = self.get(campaign_id)
        result["reconcile_receipts"] = receipts
        return result

    def _run_completion_gate_phase(self, campaign_id: str) -> dict[str, Any]:
        row = self._require(campaign_id)
        if str(row["status"]) != "COMPLETION_GATE":
            raise ValueError("completion gate phase requires COMPLETION_GATE state")
        receipts: list[dict[str, Any]] = []
        for argv in self._default_completion_gate_commands():
            receipts.append(self.execute(campaign_id, argv))
        now = datetime.now(UTC)
        passed = all(item.get("result") == "PASSED" for item in receipts)
        with self._db:
            if passed:
                self._db.execute(
                    """
                    UPDATE campaign_runs
                    SET stage = 'COMPLETE', status = 'FINALIZED', next_transition = NULL,
                        last_heartbeat_utc = ?, last_probe = ?
                    WHERE campaign_id = ?
                    """,
                    (now.isoformat(), "completion-gate-passed", campaign_id),
                )
                self._append_event(
                    campaign_id,
                    "COMPLETION_GATE_PASSED",
                    "FINALIZED",
                    {"receipts": [item.get("receipt_id") for item in receipts]},
                    now,
                )
            else:
                self._db.execute(
                    """
                    UPDATE campaign_runs
                    SET status = 'FAILED', last_heartbeat_utc = ?, last_probe = ?
                    WHERE campaign_id = ?
                    """,
                    (now.isoformat(), "completion-gate-failed", campaign_id),
                )
                self._append_event(
                    campaign_id,
                    "COMPLETION_GATE_FAILED",
                    "FAILED",
                    {"receipts": [item.get("receipt_id") for item in receipts]},
                    now,
                )
        result = self.get(campaign_id)
        result["completion_gate_receipts"] = receipts
        return result

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
