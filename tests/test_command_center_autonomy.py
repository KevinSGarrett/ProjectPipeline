from __future__ import annotations

import sys
from pathlib import Path

from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.recovery import recover_lane_loss
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor
from project_pipeline.command_center.autonomy import project_autonomy_runtime


def test_autonomy_projection_shows_external_block_and_completed(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(tmp_path / "sup.db")
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000384",
        input_fingerprint="in",
        worker_id="w",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="f",
        idempotency_key="cc-1",
        payload={"command": [sys.executable, "-c", "print('x')"]},
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.record_result(
        operation_id=operation_id,
        worker_id="w",
        output_fingerprint="out",
        status="RESULT_OBSERVED",
        payload={"ok": True},
    )
    supervisor.mark_verified(operation_id, "v")
    supervisor.mark_integrated(operation_id, "a" * 40)
    supervisor.complete_operation(operation_id)
    supervisor.close()
    registry = LaneRegistry(tmp_path / "lanes.db")
    blocked = registry.claim(
        lane_id="lane-blocked",
        worker_id="blocked",
        resources=("PATH:blocked",),
        lease_seconds=30,
    )
    healthy = registry.claim(
        lane_id="lane-healthy",
        worker_id="healthy",
        resources=("PATH:healthy",),
        lease_seconds=30,
    )
    assert blocked is not None and healthy is not None
    recover_lane_loss(
        registry=registry,
        lane_id="lane-blocked",
        stale_fencing_token="wrong",
        stale_worker_id="unknown",
    )
    registry.record_result(
        lane_id="lane-healthy",
        worker_id="healthy",
        fencing_token=healthy.fencing_token,
        result_fingerprint="done",
    )
    registry.close()
    snapshot = project_autonomy_runtime(
        supervisor_state=tmp_path / "sup.db",
        lane_state=tmp_path / "lanes.db",
        service_root=tmp_path / "svc",
        ready_task_ids=["PP-TASK-000384", "PP-TASK-000385"],
        provider_status={"label": "local", "live_qualification": False},
    )
    assert snapshot["context_summary"]["source"] == "durable_state"
    assert snapshot["context_summary"]["last_verified_sha"] == "a" * 40
    assert snapshot["context_summary"]["next_eligible_task_id"] == "PP-TASK-000385"
    assert snapshot["active_incident_ids"]
    states = {item["state"] for item in snapshot["live_work"]}
    assert "BLOCKED_EXTERNAL" in states
    assert "HUMAN" + "_REQUIRED" not in states
    assert "COMPLETED" in states
    assert snapshot["context_summary"]["unavailable_capabilities"]
    assert "lane-healthy" in snapshot["context_summary"]["continuing_lane_ids"]
    assert snapshot["provider_summary"]["label"] == "local"
    restarted = project_autonomy_runtime(
        supervisor_state=tmp_path / "sup.db",
        lane_state=tmp_path / "lanes.db",
        ready_task_ids=["PP-TASK-000384", "PP-TASK-000385"],
    )
    assert (
        restarted["context_summary"]["last_verified_sha"]
        == snapshot["context_summary"]["last_verified_sha"]
    )
