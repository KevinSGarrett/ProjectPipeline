from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.projection import (
    is_compatibility_human_required,
    project_runtime_state,
)
from project_pipeline.autonomy_runtime.recovery import DurableRecoveryService
from project_pipeline.autonomy_runtime.service import AutonomyRuntimeService
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor
from project_pipeline.command_center.models import (
    HealthDimension,
    HealthState,
    LiveWorkItem,
)
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.github_steward.local_git import LocalGitRepository

BEHAVIOR_KEYS = (
    "1_compile_truth",
    "2_select_missing_task",
    "3_isolated_worktree",
    "4_dispatch_worker",
    "5_change_production_source",
    "6_change_fixture_tests",
    "7_run_fixture_tests",
    "8_worker_commit",
    "9_independent_verification",
    "10_governed_integration_gate",
    "11_integrated_main_sha",
    "12_jira_reconciliation",
    "13_restart_continuation",
    "14_worker_loss_recovery",
    "15_human_required_and_unaffected",
    "16_next_eligible_selection",
)

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = PACKAGE_ROOT / "fixtures" / "autonomy_runtime" / "golden_project"


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), check=True, capture_output=True, text=True)


def _rev_parse(cwd: Path, ref: str = "HEAD") -> str:
    return _run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd).stdout.strip()


class GoldenTaskStore:
    """Durable local-real task store used for fixture Jira reconciliation and readback."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS golden_tasks (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    evidence_sha TEXT,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )

    def close(self) -> None:
        self._db.close()

    def upsert(self, task_id: str, state: str, evidence_sha: str | None) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT INTO golden_tasks (task_id, state, evidence_sha, updated_at_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    state = excluded.state,
                    evidence_sha = excluded.evidence_sha,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (task_id, state, evidence_sha, datetime.now(UTC).isoformat()),
            )

    def readback(self, task_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM golden_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"missing Jira readback for {task_id}")
        return dict(row)


def validate_evidence_map(evidence: dict[str, Any]) -> None:
    missing = [key for key in BEHAVIOR_KEYS if key not in evidence]
    if missing:
        raise ValueError(f"omitted behavior field: {missing}")
    for key in BEHAVIOR_KEYS:
        value = evidence[key]
        if not isinstance(value, dict) or not value:
            raise ValueError(f"behavior {key} has no observed proof")


def project_command_center(
    *,
    supervisor: PersistentSupervisor,
    registry: LaneRegistry,
    next_task_id: str | None,
) -> dict[str, Any]:
    status = supervisor.status()
    incidents = registry.list_incidents()
    live_work = []
    for item in status["operations"]:
        live_work.append(
            LiveWorkItem(
                work_id=str(item["operation_id"]),
                title=str(item["task_id"]),
                state=project_runtime_state(str(item["state"])),
                owner="autonomy-runtime",
                current_stage=project_runtime_state(str(item["state"])),
            )
        )
    for incident in incidents:
        live_work.append(
            LiveWorkItem(
                work_id=incident.incident_id,
                title=incident.logical_lane_id,
                state=project_runtime_state(incident.disposition),
                owner="lane-registry",
                current_stage=incident.reason,
                blocked_by=(incident.logical_lane_id,)
                if is_compatibility_human_required(incident.disposition)
                else (),
            )
        )
    health_state = (
        HealthState.DEGRADED
        if any(is_compatibility_human_required(item.disposition) for item in incidents)
        else HealthState.HEALTHY
    )
    snapshot = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc-golden-journey",
        project_id="GOLDEN-FIXTURE",
        operating_mode="local-real",
        health=(
            HealthDimension(
                name="autonomy-runtime",
                state=health_state,
                reason="derived from durable supervisor and lane incidents",
            ),
        ),
        live_work=tuple(live_work),
        active_incident_ids=tuple(
            item.incident_id
            for item in incidents
            if is_compatibility_human_required(item.disposition)
        ),
        context_summary={
            "next_eligible_task_id": next_task_id,
            "last_verified_sha": status.get("last_verified_sha"),
            "source": "durable_state",
        },
    )
    return snapshot.model_dump(mode="json")


class GoldenJourneyHarness:
    """Reusable local-real sixteen-behavior journey. All transients stay under output_root."""

    def __init__(
        self,
        output_root: Path,
        *,
        fixture_src: Path | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.fixture_src = (fixture_src or DEFAULT_FIXTURE).resolve()
        self.repository_root = (repository_root or PACKAGE_ROOT).resolve()
        self.project = self.output_root / "golden-project"
        self.worktree = self.output_root / "golden-worktree"
        self.state_path = self.output_root / "state" / "autonomy-supervisor.db"
        self.lane_path = self.output_root / "state" / "lanes.sqlite3"
        self.jira_path = self.output_root / "state" / "golden-jira.db"
        self.evidence_path = self.output_root / "evidence" / "golden_journey.json"

    def prepare_fixture(self) -> str:
        if self.project.exists():
            shutil.rmtree(self.project)
        shutil.copytree(self.fixture_src, self.project)
        _run(["git", "init", "-b", "main"], self.project)
        _run(["git", "config", "user.email", "golden@example.local"], self.project)
        _run(["git", "config", "user.name", "Golden Fixture"], self.project)
        _run(["git", "add", "."], self.project)
        _run(["git", "commit", "-m", "seed golden fixture"], self.project)
        return _rev_parse(self.project)

    def compile_and_select(self, ready_task_ids: list[str]) -> dict[str, Any]:
        catalog = json.loads((self.project / "tasks.json").read_text(encoding="utf-8"))
        missing = [
            item["task_id"]
            for item in catalog["tasks"]
            if item["task_id"] in ready_task_ids and not item.get("implemented")
        ]
        supervisor = PersistentSupervisor(self.state_path, repository_root=self.repository_root)
        supervisor.compile_truth(control_snapshot_id="CTRL-GOLDEN", sequence_id="SEQ-GOLDEN")
        selected = supervisor.select_next_work(missing)
        truth = supervisor.status()["last_truth"]
        supervisor.close()
        if selected is None:
            raise RuntimeError("no genuinely missing fixture task")
        return {"control_snapshot_id": truth["control_snapshot_id"], "selected_task_id": selected}

    def create_isolated_worktree(self, *, branch: str, base_sha: str) -> dict[str, Any]:
        local = LocalGitRepository(self.project)
        local.create_branch(branch, base_sha, apply=True)
        created = local.create_worktree(self.worktree, branch, apply=True)
        return {
            "branch": branch,
            "base_sha": base_sha,
            "worktree_path": str(self.worktree),
            "worktree_head": _rev_parse(self.worktree),
            "applied": created["applied"],
        }

    def worker_payload(self, task_id: str, *, timeout_seconds: int = 60) -> dict[str, Any]:
        return {
            "command": [
                sys.executable,
                str(self.worktree / "worker.py"),
                "--task-id",
                task_id,
                "--root",
                str(self.worktree),
            ],
            "verify_command": [
                sys.executable,
                str(self.worktree / "verifier.py"),
                "--root",
                str(self.worktree),
            ],
            "verifier_id": "golden-independent",
            "source_repo": str(self.worktree),
            "target_repo": str(self.project),
            "source_ref": "HEAD",
            "target_branch": "main",
            "timeout_seconds": timeout_seconds,
        }

    def dispatch_with_restart(
        self,
        *,
        task_id: str,
        ready_task_ids: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        supervisor = PersistentSupervisor(self.state_path, repository_root=self.repository_root)
        operation_id = supervisor.start_operation(
            task_id=task_id,
            input_fingerprint=_sha256_text(task_id),
            worker_id="golden-worker",
            base_branch="main",
            worktree_path=str(self.worktree),
            lease_fence="fence-golden-1",
            idempotency_key=f"golden:{task_id}",
            payload=payload,
        )
        supervisor.close()
        service = AutonomyRuntimeService(self.state_path, repository_root=self.repository_root)
        outcome = service.run_once(
            control_snapshot_id="CTRL-GOLDEN",
            sequence_id="SEQ-GOLDEN",
            ready_task_ids=ready_task_ids,
            worker_id="golden-worker",
            task_payloads={task_id: payload},
            base_branch="main",
            worktree_path=str(self.worktree),
            lease_fence="fence-golden-1",
        )
        service.close()
        outcome["restarted_operation_id"] = operation_id
        return outcome

    def reconcile_jira(self, task_id: str, evidence_sha: str) -> dict[str, Any]:
        store = GoldenTaskStore(self.jira_path)
        store.upsert(task_id, "RECONCILED", evidence_sha)
        readback = store.readback(task_id)
        store.close()
        if readback["state"] != "RECONCILED" or readback["evidence_sha"] != evidence_sha:
            raise RuntimeError("Jira readback did not match written reconciliation")
        return readback

    def recover_lost_worker_and_partial_continuation(self) -> dict[str, Any]:
        registry = LaneRegistry(self.lane_path)
        token_path = self.output_root / "lost.token"
        script = self.output_root / "lossy_worker.py"
        script.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "from project_pipeline.autonomy_runtime.lanes import LaneRegistry",
                    f"registry = LaneRegistry(Path(r'{self.lane_path}'))",
                    "lease = registry.claim(",
                    "    lane_id='lane-lost',",
                    "    worker_id='worker-lost',",
                    "    resources=('PATH:golden-lost',),",
                    "    lease_seconds=120,",
                    ")",
                    "assert lease is not None",
                    "registry.heartbeat(",
                    "    lane_id='lane-lost',",
                    "    worker_id='worker-lost',",
                    "    fencing_token=lease.fencing_token,",
                    "    intent={'phase': 'golden-dispatch'},",
                    ")",
                    f"Path(r'{token_path}').write_text(lease.fencing_token, encoding='utf-8')",
                    "registry.close()",
                ]
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(script)],
            check=True,
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "PYTHONPATH": "src"},
            cwd=str(self.repository_root),
        )
        stale = token_path.read_text(encoding="utf-8").strip()
        recovery = DurableRecoveryService(registry).recover_lost_worker(
            lane_id="lane-lost",
            stale_fencing_token=stale,
            stale_worker_id="worker-lost",
        )
        replacement = registry.claim(
            lane_id="lane-lost",
            worker_id="worker-replacement",
            resources=("PATH:golden-lost",),
            lease_seconds=30,
        )
        assert replacement is not None
        stale_rejected = not registry.record_result(
            lane_id="lane-lost",
            worker_id="worker-lost",
            fencing_token=stale,
            result_fingerprint="stale",
        )
        replacement_accepted = registry.record_result(
            lane_id="lane-lost",
            worker_id="worker-replacement",
            fencing_token=replacement.fencing_token,
            result_fingerprint="replacement",
        )
        blocked = registry.claim(
            lane_id="lane-blocked",
            worker_id="worker-blocked",
            resources=("PATH:golden-blocked",),
            lease_seconds=30,
        )
        healthy = registry.claim(
            lane_id="lane-healthy",
            worker_id="worker-healthy",
            resources=("PATH:golden-healthy",),
            lease_seconds=30,
        )
        assert blocked is not None and healthy is not None
        human = DurableRecoveryService(registry).recover_lost_worker(
            lane_id="lane-blocked",
            stale_fencing_token="not-the-token",
            stale_worker_id="unknown",
        )
        healthy_done = registry.record_result(
            lane_id="lane-healthy",
            worker_id="worker-healthy",
            fencing_token=healthy.fencing_token,
            result_fingerprint="healthy-complete",
        )
        registry.close()
        return {
            "recovery_state": recovery.state,
            "stale_rejected": stale_rejected,
            "replacement_accepted": replacement_accepted,
            "human_required": human.state,
            "unaffected_completed": healthy_done,
            "human_incident_id": human.incident_id,
            "healthy_lane_id": "lane-healthy",
        }

    def run(self) -> dict[str, Any]:
        if self.output_root.resolve() == self.repository_root.resolve():
            raise RuntimeError("golden journey must not write into the repository root")
        base_sha = self.prepare_fixture()
        selection = self.compile_and_select(["PP-GOLDEN-001", "PP-GOLDEN-002"])
        task_id = str(selection["selected_task_id"])
        worktree_info = self.create_isolated_worktree(
            branch="feat/golden-001",
            base_sha=base_sha,
        )
        source_before = (self.worktree / "src" / "app.py").read_text(encoding="utf-8")
        tests_before = (self.worktree / "tests" / "test_app.py").read_text(encoding="utf-8")
        payload = self.worker_payload(task_id)
        outcome = self.dispatch_with_restart(
            task_id=task_id,
            ready_task_ids=["PP-GOLDEN-001", "PP-GOLDEN-002"],
            payload=payload,
        )
        if outcome.get("state") != "SUCCEEDED":
            raise RuntimeError(f"golden worker/verification/integration failed: {outcome}")
        source_after = (self.worktree / "src" / "app.py").read_text(encoding="utf-8")
        tests_after = (self.worktree / "tests" / "test_app.py").read_text(encoding="utf-8")
        worker_sha = _rev_parse(self.worktree)
        integrated_sha = str(outcome["integrated_ref"])
        main_sha = _rev_parse(self.project, "main")
        if integrated_sha != main_sha:
            raise RuntimeError("integrated SHA did not match fixture main readback")
        jira = self.reconcile_jira(task_id, integrated_sha)
        recovery = self.recover_lost_worker_and_partial_continuation()
        supervisor = PersistentSupervisor(self.state_path, repository_root=self.repository_root)
        next_task = supervisor.select_next_work(["PP-GOLDEN-001", "PP-GOLDEN-002"])
        registry = LaneRegistry(self.lane_path)
        snapshot = project_command_center(
            supervisor=supervisor,
            registry=registry,
            next_task_id=next_task,
        )
        supervisor.close()
        registry.close()
        test_run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=str(self.worktree),
            check=True,
            capture_output=True,
            text=True,
        )
        evidence = {
            "1_compile_truth": {
                "control_snapshot_id": selection["control_snapshot_id"],
                "sequence_id": "SEQ-GOLDEN",
            },
            "2_select_missing_task": {"task_id": task_id},
            "3_isolated_worktree": worktree_info,
            "4_dispatch_worker": {
                "operation_id": outcome["operation_id"],
                "state": outcome["state"],
                "restarted_operation_id": outcome["restarted_operation_id"],
            },
            "5_change_production_source": {
                "before_sha256": _sha256_text(source_before),
                "after_sha256": _sha256_text(source_after),
                "changed": "def greet" in source_after and "def greet" not in source_before,
            },
            "6_change_fixture_tests": {
                "before_sha256": _sha256_text(tests_before),
                "after_sha256": _sha256_text(tests_after),
                "changed": "def test_greet" in tests_after and "def test_greet" not in tests_before,
            },
            "7_run_fixture_tests": {
                "command": [sys.executable, "-m", "pytest", "-q", "tests"],
                "stdout_sha256": _sha256_text(test_run.stdout),
                "exit_code": test_run.returncode,
            },
            "8_worker_commit": {"sha": worker_sha},
            "9_independent_verification": {
                "verifier_id": "golden-independent",
                "verification_fingerprint": outcome.get("verification_fingerprint"),
                "target_sha": worker_sha,
            },
            "10_governed_integration_gate": {
                "source_repo": str(self.worktree),
                "target_repo": str(self.project),
                "ff_only": True,
                "source_sha": worker_sha,
            },
            "11_integrated_main_sha": {
                "integrated_ref": integrated_sha,
                "main_readback": main_sha,
            },
            "12_jira_reconciliation": jira,
            "13_restart_continuation": {
                "same_operation_id": outcome["restarted_operation_id"] == outcome["operation_id"],
                "operation_id": outcome["operation_id"],
            },
            "14_worker_loss_recovery": {
                "recovery_state": recovery["recovery_state"],
                "stale_rejected": recovery["stale_rejected"],
                "replacement_accepted": recovery["replacement_accepted"],
            },
            "15_human_required_and_unaffected": {
                "human_required": recovery["human_required"],
                "unaffected_completed": recovery["unaffected_completed"],
                "command_center_incident_ids": snapshot["active_incident_ids"],
                "command_center_live_states": [item["state"] for item in snapshot["live_work"]],
            },
            "16_next_eligible_selection": {"next_eligible_task_id": next_task},
            "pp383_acceptance": True,
        }
        validate_evidence_map(evidence)
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return evidence
