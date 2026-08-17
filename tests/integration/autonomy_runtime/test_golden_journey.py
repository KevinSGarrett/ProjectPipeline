from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.service import AutonomyRuntimeService
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor

ROOT = Path(__file__).resolve().parents[3]


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)


def test_local_real_golden_journey(tmp_path: Path) -> None:
    fixture_src = ROOT / "fixtures" / "autonomy_runtime" / "golden_project"
    project = tmp_path / "golden-project"
    shutil.copytree(fixture_src, project)

    _run(["git", "init", "-b", "main"], project)
    _run(["git", "config", "user.email", "golden@example.local"], project)
    _run(["git", "config", "user.name", "Golden Fixture"], project)
    _run(["git", "add", "."], project)
    _run(["git", "commit", "-m", "seed"], project)
    _run(["git", "switch", "-c", "feat/golden-runtime"], project)

    payloads = {
        "PP-TASK-000383": {"command": [sys.executable, "-c", "print('383')"]},
        "PP-TASK-000384": {"command": [sys.executable, "-c", "print('384')"]},
    }
    state_path = tmp_path / "state" / "autonomy-supervisor.db"
    service = AutonomyRuntimeService(state_path)
    outcome_one = service.run_once(
        control_snapshot_id="CTRL-GOLDEN-001",
        sequence_id="SEQ-GOLDEN-001",
        ready_task_ids=["PP-TASK-000383", "PP-TASK-000384"],
        worker_id="worker-golden-a",
        task_payloads=payloads,
        base_branch="main",
        worktree_path=str(project),
        lease_fence="fence-golden-a",
    )
    assert outcome_one["state"] == "SUCCEEDED"
    assert outcome_one["task_id"] == "PP-TASK-000383"
    service.close()

    restarted = AutonomyRuntimeService(state_path)
    outcome_two = restarted.run_once(
        control_snapshot_id="CTRL-GOLDEN-002",
        sequence_id="SEQ-GOLDEN-002",
        ready_task_ids=["PP-TASK-000383", "PP-TASK-000384"],
        worker_id="worker-golden-b",
        task_payloads=payloads,
        base_branch="main",
        worktree_path=str(project),
        lease_fence="fence-golden-b",
    )
    assert outcome_two["state"] == "SUCCEEDED"
    assert outcome_two["task_id"] == "PP-TASK-000384"
    restarted.close()

    lane_db = tmp_path / "state" / "lanes.sqlite3"
    registry = LaneRegistry(lane_db)
    lane_a = registry.claim(
        lane_id="lane-a",
        worker_id="worker-a",
        resources=("PATH:shared-exclusive",),
        lease_seconds=5,
    )
    lane_b = registry.claim(
        lane_id="lane-b",
        worker_id="worker-b",
        resources=("PATH:independent",),
        lease_seconds=5,
    )
    assert lane_a is not None
    assert lane_b is not None
    assert registry.record_result(
        lane_id="lane-b",
        worker_id="worker-b",
        fencing_token=lane_b.fencing_token,
        result_fingerprint="lane-b-complete",
    )
    unknown = PersistentSupervisor(tmp_path / "state" / "unknown.db")
    unknown_id = unknown.start_operation(
        task_id="PP-TASK-000383",
        input_fingerprint="in:unknown",
        worker_id="worker-unknown",
        base_branch="main",
        worktree_path=str(project),
        lease_fence="fence-unknown",
        idempotency_key="golden-unknown",
        payload={"command": [sys.executable, "-c", "print('unknown')"]},
    )
    unknown.mark_dispatched(unknown_id)
    unknown.mark_unknown_outcome(unknown_id)
    unknown.reconcile_unknown_outcome(unknown_id, applied=False)
    unknown.complete_operation(unknown_id)
    unknown.close()
    registry.close()

    evidence_dir = tmp_path / "evidence" / "autonomy_runtime" / "golden_journey"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "golden_journey_latest.json"
    evidence_payload = {
        "schema_version": "1.0.0",
        "fixture_git_branch": "feat/golden-runtime",
        "completed_tasks": ["PP-TASK-000383", "PP-TASK-000384"],
        "restart_continuation_verified": True,
        "unknown_outcome_reconcile_verified": True,
        "unaffected_lane_completion_verified": True,
        "pp383_acceptance": False,
        "note": "Compatibility fixture only; PP-383 requires the sixteen-behavior harness.",
    }
    evidence_path.write_text(json.dumps(evidence_payload, indent=2) + "\n", encoding="utf-8")

    (project / "runtime_receipt.txt").write_text(
        f"{outcome_one['operation_id']}\n{outcome_two['operation_id']}\n",
        encoding="utf-8",
    )
    _run(["git", "add", "."], project)
    _run(["git", "commit", "-m", "golden journey output"], project)
    log = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=str(project),
        check=True,
        capture_output=True,
        text=True,
    )
    assert len(log.stdout.strip()) == 40
