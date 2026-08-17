from __future__ import annotations

from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.service import AutonomyRuntimeService
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "autonomy-supervisor.json"


def test_supervisor_state_survives_restart(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    first = PersistentSupervisor(path)
    operation_id = first.start_operation(task_id="PP-TASK-000381", input_fingerprint="in:1")
    first.record_result(
        operation_id=operation_id,
        worker_id="worker-A",
        output_fingerprint="out:1",
        status="SUCCEEDED",
    )

    second = PersistentSupervisor(path)
    status = second.status()
    assert status["operation_count"] == 1
    assert status["receipt_count"] == 1
    assert status["active_operation_id"] == operation_id


def test_duplicate_result_replay_is_idempotent(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(_state_path(tmp_path))
    operation_id = supervisor.start_operation(task_id="PP-TASK-000381", input_fingerprint="in:1")
    one = supervisor.record_result(
        operation_id=operation_id,
        worker_id="worker-A",
        output_fingerprint="out:1",
        status="SUCCEEDED",
    )
    two = supervisor.record_result(
        operation_id=operation_id,
        worker_id="worker-A",
        output_fingerprint="out:1",
        status="SUCCEEDED",
    )
    assert one.output_fingerprint == two.output_fingerprint
    assert one.status == two.status


def test_unknown_outcome_requires_reconcile_before_completion(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(_state_path(tmp_path))
    operation_id = supervisor.start_operation(task_id="PP-TASK-000381", input_fingerprint="in:1")
    supervisor.mark_unknown_outcome(operation_id)
    with pytest.raises(ValueError):
        supervisor.complete_operation(operation_id)
    supervisor.reconcile_unknown_outcome(operation_id, applied=False)
    supervisor.complete_operation(operation_id)
    assert "PP-TASK-000381" in supervisor.status()["completed_tasks"]


def test_no_ready_work_reports_idle(tmp_path: Path) -> None:
    service = AutonomyRuntimeService(_state_path(tmp_path))
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-TEST",
        ready_task_ids=[],
        worker_id="worker-A",
    )
    assert outcome["state"] == "IDLE"
    assert outcome["reason"] == "NO_READY_WORK"


def test_cancellation_preserves_receipt_record(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(_state_path(tmp_path))
    operation_id = supervisor.start_operation(task_id="PP-TASK-000381", input_fingerprint="in:1")
    supervisor.record_result(
        operation_id=operation_id,
        worker_id="worker-A",
        output_fingerprint="out:1",
        status="SUCCEEDED",
    )
    supervisor.cancel_operation(operation_id)
    status = supervisor.status()
    assert status["receipt_count"] == 1
    assert status["active_operation_id"] is None
