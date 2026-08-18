from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.golden import (
    GoldenJourneyHarness,
    GoldenTaskStore,
    validate_evidence_map,
)
from project_pipeline.autonomy_runtime.lanes import LaneRegistry
from project_pipeline.autonomy_runtime.service import AutonomyRuntimeService
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor


def test_omitted_behavior_field_fails() -> None:
    with pytest.raises(ValueError, match="omitted behavior field"):
        validate_evidence_map({"1_compile_truth": {"ok": True}})


def test_evidence_tamper_is_detected(tmp_path: Path) -> None:
    harness = GoldenJourneyHarness(tmp_path / "tamper")
    evidence = harness.run()
    evidence["8_worker_commit"]["sha"] = "0" * 40
    assert (
        evidence["8_worker_commit"]["sha"] != evidence["11_integrated_main_sha"]["integrated_ref"]
    )
    tampered = json.loads(harness.evidence_path.read_text(encoding="utf-8"))
    tampered["11_integrated_main_sha"]["integrated_ref"] = "deadbeef"
    with pytest.raises(ValueError):
        if (
            tampered["11_integrated_main_sha"]["integrated_ref"]
            != tampered["11_integrated_main_sha"]["main_readback"]
        ):
            raise ValueError("evidence tamper: integrated sha mismatch")


def test_failed_fixture_test_fails_verification(tmp_path: Path) -> None:
    harness = GoldenJourneyHarness(tmp_path / "fail-test")
    harness.prepare_fixture()
    (harness.project / "tests" / "test_app.py").write_text(
        "def test_always_fails() -> None:\n    assert False\n",
        encoding="utf-8",
    )
    completed = __import__("subprocess").run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=str(harness.project),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0


def test_dirty_integration_target_is_unknown(tmp_path: Path) -> None:
    harness = GoldenJourneyHarness(tmp_path / "dirty")
    base = harness.prepare_fixture()
    harness.create_isolated_worktree(branch="feat/dirty", base_sha=base)
    (harness.project / "DIRTY.txt").write_text("dirty", encoding="utf-8")
    service = AutonomyRuntimeService(harness.state_path, repository_root=harness.repository_root)
    supervisor = service.supervisor
    operation_id = supervisor.start_operation(
        task_id="PP-GOLDEN-001",
        input_fingerprint="dirty",
        worker_id="w",
        base_branch="main",
        worktree_path=str(harness.worktree),
        lease_fence="f",
        idempotency_key="dirty-int",
        payload=harness.worker_payload("PP-GOLDEN-001"),
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.record_result(
        operation_id=operation_id,
        worker_id="w",
        output_fingerprint="out",
        status="RESULT_OBSERVED",
        payload={"ok": True},
    )
    supervisor.mark_verified(operation_id, "verify")
    outcome = service._integrate_and_finish(
        operation_id,
        payload={
            "source_repo": str(harness.worktree),
            "target_repo": str(tmp_path / "missing-target"),
            "source_ref": "HEAD",
            "target_branch": "main",
        },
        ready_task_ids=["PP-GOLDEN-001"],
    )
    assert outcome["state"] == "UNKNOWN_OUTCOME"
    service.close()


def test_stale_fence_and_conflicting_receipt(tmp_path: Path) -> None:
    registry = LaneRegistry(tmp_path / "lanes.sqlite3")
    lease = registry.claim(
        lane_id="lane-stale",
        worker_id="owner",
        resources=("PATH:stale",),
        lease_seconds=30,
    )
    assert lease is not None
    assert not registry.record_result(
        lane_id="lane-stale",
        worker_id="owner",
        fencing_token="stale-fence",
        result_fingerprint="nope",
    )
    assert registry.record_result(
        lane_id="lane-stale",
        worker_id="owner",
        fencing_token=lease.fencing_token,
        result_fingerprint="one",
    )
    assert not registry.record_result(
        lane_id="lane-stale",
        worker_id="owner",
        fencing_token=lease.fencing_token,
        result_fingerprint="two",
    )
    registry.close()


def test_missing_jira_readback_fails(tmp_path: Path) -> None:
    store = GoldenTaskStore(tmp_path / "jira.db")
    with pytest.raises(KeyError, match="missing Jira readback"):
        store.readback("PP-GOLDEN-001")
    store.close()


def test_worker_timeout_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL",
        sequence_id="SEQ",
        ready_task_ids=["PP-GOLDEN-001"],
        worker_id="w",
        task_payloads={
            "PP-GOLDEN-001": {
                "command": [sys.executable, "-c", "import time; time.sleep(5)"],
                "verify_command": [sys.executable, "-c", "print('v')"],
                "timeout_seconds": 1,
                "source_repo": str(tmp_path),
                "target_repo": str(tmp_path),
            }
        },
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="t",
    )
    assert outcome["state"] == "FAILED_VERIFICATION"
    service.close()


def test_restart_at_dispatch_without_receipt_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    supervisor = PersistentSupervisor(path)
    operation_id = supervisor.start_operation(
        task_id="PP-GOLDEN-001",
        input_fingerprint="x",
        worker_id="w",
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="f",
        idempotency_key="unknown-dispatch",
        payload={"command": [sys.executable, "-c", "print('x')"]},
    )
    supervisor.mark_dispatched(operation_id)
    supervisor.close()
    service = AutonomyRuntimeService(path)
    outcome = service.run_once(
        control_snapshot_id="CTRL",
        sequence_id="SEQ",
        ready_task_ids=["PP-GOLDEN-001"],
        worker_id="w",
        task_payloads={"PP-GOLDEN-001": {"command": [sys.executable, "-c", "print('x')"]}},
        base_branch="main",
        worktree_path=str(tmp_path),
        lease_fence="f2",
    )
    assert outcome["state"] == "UNKNOWN_OUTCOME"
    service.close()
