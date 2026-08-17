from __future__ import annotations

from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.service import AutonomyRuntimeService
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "autonomy-supervisor.db"


def _task_payload(target: Path, value: str) -> dict[str, dict[str, object]]:
    command = [
        "python",
        "-c",
        (
            "from pathlib import Path; "
            f"Path(r'{target.as_posix()}').write_text('{value}', encoding='utf-8')"
        ),
    ]
    return {"PP-TASK-000381": {"command": command}}


def test_supervisor_state_survives_restart(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    fixture = tmp_path / "runtime-fixture.txt"
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-TEST",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-A",
        task_payloads=_task_payload(fixture, "first"),
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
    )
    assert outcome["state"] == "SUCCEEDED"
    assert fixture.read_text(encoding="utf-8") == "first"
    service.close()

    second = PersistentSupervisor(path, repository_root=Path.cwd())
    status = second.status()
    assert status["operation_count"] == 1
    assert status["receipt_count"] == 1
    assert status["active_operation_id"] is None
    second.close()


def test_duplicate_result_replay_is_idempotent(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(_state_path(tmp_path), repository_root=Path.cwd())
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:1",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
        idempotency_key="idempotent-1",
        payload={"command": ["python", "-c", "print('ok')"]},
    )
    supervisor.mark_dispatched(operation_id)
    one = supervisor.record_result(
        operation_id=operation_id,
        worker_id="worker-A",
        output_fingerprint="out:1",
        status="RESULT_OBSERVED",
        payload={"result": 1},
    )
    two = supervisor.record_result(
        operation_id=operation_id,
        worker_id="worker-A",
        output_fingerprint="out:1",
        status="RESULT_OBSERVED",
        payload={"result": 1},
    )
    assert one.output_fingerprint == two.output_fingerprint
    assert one.status == two.status
    with pytest.raises(ValueError):
        supervisor.record_result(
            operation_id=operation_id,
            worker_id="worker-A",
            output_fingerprint="out:2",
            status="RESULT_OBSERVED",
            payload={"result": 2},
        )
    supervisor.close()


def test_unknown_outcome_requires_reconcile_before_completion(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(_state_path(tmp_path), repository_root=Path.cwd())
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:1",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
        idempotency_key="idempotent-unknown",
        payload={"command": ["python", "-c", "print('ok')"]},
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.mark_unknown_outcome(operation_id)
    with pytest.raises(ValueError):
        supervisor.complete_operation(operation_id)
    supervisor.reconcile_unknown_outcome(operation_id, applied=False)
    supervisor.complete_operation(operation_id)
    assert "PP-TASK-000381" in supervisor.status()["completed_tasks"]
    supervisor.close()


def test_no_ready_work_reports_idle(tmp_path: Path) -> None:
    service = AutonomyRuntimeService(_state_path(tmp_path))
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-TEST",
        ready_task_ids=[],
        worker_id="worker-A",
        task_payloads={},
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
    )
    assert outcome["state"] == "IDLE"
    assert outcome["reason"] == "NO_READY_WORK"
    service.close()


def test_restart_continues_with_same_operation_when_active(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(_state_path(tmp_path), repository_root=Path.cwd())
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:1",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
        idempotency_key="replay-key",
        payload={"command": ["python", "-c", "print('ok')"]},
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.close()

    service = AutonomyRuntimeService(_state_path(tmp_path))
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-TEST",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-B",
        task_payloads={"PP-TASK-000381": {"command": ["python", "-c", "print('new')"]}},
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-2",
    )
    assert outcome["state"] == "WAITING_FOR_RECONCILIATION"
    assert outcome["operation_id"] == operation_id
    status = service.supervisor.status()
    assert status["active_operation_id"] == operation_id
    service.close()
