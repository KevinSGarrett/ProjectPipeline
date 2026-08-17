from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.service import AutonomyRuntimeService
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "autonomy-supervisor.db"


def _init_git(repo: Path) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "pp381@example.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "PP381"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _task_payload(
    repo: Path, value: str, task_id: str = "PP-TASK-000381"
) -> dict[str, dict[str, object]]:
    command = [
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            f"Path(r'{repo.as_posix()}', 'out.txt').write_text('{value}', encoding='utf-8'); "
            "print('ok')"
        ),
    ]
    verify = [sys.executable, "-c", "print('verified')"]
    return {
        task_id: {
            "command": command,
            "verify_command": verify,
            "verifier_id": "pp381-local-verifier",
            "source_repo": str(repo),
            "target_repo": str(repo),
            "source_ref": "HEAD",
            "target_branch": "main",
        }
    }


def test_supervisor_state_survives_restart(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    _init_git(repo)
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-TEST",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-A",
        task_payloads=_task_payload(repo, "first"),
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-1",
    )
    assert outcome["state"] == "SUCCEEDED"
    assert (repo / "out.txt").read_text(encoding="utf-8") == "first"
    assert len(str(outcome["integrated_ref"])) == 40
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
        payload={"command": [sys.executable, "-c", "print('ok')"]},
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
        payload={"command": [sys.executable, "-c", "print('ok')"]},
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


def test_restart_resumes_unknown_dispatch_without_blind_retry(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    supervisor = PersistentSupervisor(path, repository_root=Path.cwd())
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:1",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
        idempotency_key="replay-key",
        payload={"command": [sys.executable, "-c", "print('ok')"]},
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.close()

    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-TEST",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-B",
        task_payloads={"PP-TASK-000381": {"command": [sys.executable, "-c", "print('new')"]}},
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-2",
    )
    assert outcome["state"] == "UNKNOWN_OUTCOME"
    assert outcome["operation_id"] == operation_id
    assert outcome["resumed"] is True
    assert service.supervisor.status()["active_operation_state"] == "UNKNOWN_OUTCOME"
    service.close()


def test_duplicate_idempotency_reconciles_and_conflict_fails(tmp_path: Path) -> None:
    supervisor = PersistentSupervisor(_state_path(tmp_path), repository_root=Path.cwd())
    first = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:1",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
        idempotency_key="same-key",
        payload={"command": ["python", "-c", "print('ok')"]},
    )
    replay = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:1",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="lease-1",
        idempotency_key="same-key",
        payload={"command": ["python", "-c", "print('ok')"]},
    )
    assert first == replay
    with pytest.raises(ValueError, match="idempotency key conflict"):
        supervisor.start_operation(
            task_id="PP-TASK-000381",
            input_fingerprint="in:2",
            worker_id="worker-A",
            base_branch="main",
            worktree_path=str(tmp_path),
            lease_fence="lease-1",
            idempotency_key="same-key",
            payload={"command": ["python", "-c", "print('other')"]},
        )
    supervisor.close()


def test_failed_verification_never_enters_verified_result(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    _init_git(repo)
    payloads = _task_payload(repo, "fail")
    payloads["PP-TASK-000381"]["verify_command"] = [sys.executable, "-c", "raise SystemExit(1)"]
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-FAIL",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-A",
        task_payloads=payloads,
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-fail",
    )
    assert outcome["state"] == "FAILED_VERIFICATION"
    record = service.supervisor.operation_record(outcome["operation_id"])
    assert record["state"] == "FAILED"
    assert record["state"] != "VERIFIED_RESULT"
    service.close()


def test_timeout_and_invalid_worktree_fail_closed(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    _init_git(repo)
    payloads = _task_payload(repo, "slow")
    payloads["PP-TASK-000381"]["command"] = [
        sys.executable,
        "-c",
        "import time; time.sleep(5)",
    ]
    payloads["PP-TASK-000381"]["timeout_seconds"] = 1
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-TIMEOUT",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-A",
        task_payloads=payloads,
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-timeout",
    )
    assert outcome["state"] == "FAILED_VERIFICATION"
    assert outcome["verification_reason"] == "timeout"
    service.close()

    missing = AutonomyRuntimeService(_state_path(tmp_path / "missing"))
    missing_payloads = _task_payload(repo, "x")
    outcome = missing.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-MISSING",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-A",
        task_payloads=missing_payloads,
        base_branch="main",
        worktree_path=str(tmp_path / "does-not-exist"),
        lease_fence="lease-missing",
    )
    assert outcome["state"] == "UNKNOWN_OUTCOME"
    missing.close()


def test_restart_after_intent_completes_same_operation(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    _init_git(repo)
    supervisor = PersistentSupervisor(path, repository_root=Path.cwd())
    payloads = _task_payload(repo, "resumed")
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:resume",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-1",
        idempotency_key="resume-intent",
        payload=payloads["PP-TASK-000381"],
    )
    supervisor.close()
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-RESUME",
        ready_task_ids=["PP-TASK-000381", "PP-TASK-000382"],
        worker_id="worker-B",
        task_payloads={**payloads, **_task_payload(repo, "next", "PP-TASK-000382")},
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-2",
    )
    assert outcome["state"] == "SUCCEEDED"
    assert outcome["operation_id"] == operation_id
    assert outcome["next_eligible_task_id"] == "PP-TASK-000382"
    service.close()


def test_health_reports_selection_and_verified_sha(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    _init_git(repo)
    service = AutonomyRuntimeService(path)
    service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-HEALTH",
        ready_task_ids=["PP-TASK-000381", "PP-TASK-000382"],
        worker_id="worker-A",
        task_payloads=_task_payload(repo, "health"),
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-health",
    )
    health = service.health(ready_task_ids=["PP-TASK-000381", "PP-TASK-000382"])
    assert health["state"] == "healthy"
    assert health["last_verified_task_id"] == "PP-TASK-000381"
    assert health["last_verified_sha"]
    assert health["next_eligible_task_id"] == "PP-TASK-000382"
    service.close()


def test_oversized_output_is_bounded_and_hashed(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    _init_git(repo)
    payloads = _task_payload(repo, "big")
    payloads["PP-TASK-000381"]["command"] = [
        sys.executable,
        "-c",
        "print('X' * 200000)",
    ]
    payloads["PP-TASK-000381"]["timeout_seconds"] = 10
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-BOUND",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-A",
        task_payloads=payloads,
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-bound",
    )
    assert outcome["state"] == "SUCCEEDED"
    receipt = service.supervisor.receipt_for(outcome["operation_id"])
    assert receipt is not None
    payload = json.loads(str(receipt["payload_json"]))["payload"]
    assert payload["output_truncated"] is True
    assert len(payload["stdout"]) <= 65536
    assert len(payload["stdout_sha256"]) == 64
    service.close()


def test_unknown_integration_does_not_fabricate_sha(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    _init_git(repo)
    payloads = _task_payload(repo, "integrate")
    payloads["PP-TASK-000381"]["target_repo"] = str(tmp_path / "not-a-repo")
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-INT",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-A",
        task_payloads=payloads,
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-int",
    )
    assert outcome["state"] == "UNKNOWN_OUTCOME"
    assert "INTEGRATION_UNKNOWN" in str(outcome["reason"])
    record = service.supervisor.operation_record(outcome["operation_id"])
    assert record["state"] == "UNKNOWN_OUTCOME"
    assert record["integrated_ref"] is None
    service.close()


def test_restart_after_verified_completes_same_integration(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    repo = tmp_path / "repo"
    seed = _init_git(repo)
    supervisor = PersistentSupervisor(path, repository_root=Path.cwd())
    payloads = _task_payload(repo, "verified-restart")
    operation_id = supervisor.start_operation(
        task_id="PP-TASK-000381",
        input_fingerprint="in:verified",
        worker_id="worker-A",
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-1",
        idempotency_key="verified-restart",
        payload=payloads["PP-TASK-000381"],
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.record_result(
        operation_id=operation_id,
        worker_id="worker-A",
        output_fingerprint="out:verified",
        status="RESULT_OBSERVED",
        payload={"ok": True},
    )
    supervisor.mark_verified(operation_id, "verify:1")
    supervisor.close()
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL-TEST",
        sequence_id="SEQ-VERIFIED",
        ready_task_ids=["PP-TASK-000381"],
        worker_id="worker-B",
        task_payloads=payloads,
        base_branch="main",
        worktree_path=str(repo),
        lease_fence="lease-2",
    )
    assert outcome["state"] == "SUCCEEDED"
    assert outcome["operation_id"] == operation_id
    assert outcome["integrated_ref"] == seed
    service.close()
