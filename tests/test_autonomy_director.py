from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from project_pipeline.command_center.autonomy_director import (
    AutonomyDirectorError,
    PersistentAutonomyDirector,
    evaluate_live_control,
)
from project_pipeline.control.persistence import ControlStore
from project_pipeline.domain.control import TaskEligibility, TaskReadiness
from tests.test_scheduler_engine import control_snapshot

ROOT = Path(__file__).resolve().parents[1]


def test_director_persists_selection_across_restart(tmp_path) -> None:
    path = tmp_path / "director_state.json"
    first = PersistentAutonomyDirector(path)
    control = control_snapshot(("PP-STORY-000065", "PP-STORY-000049"))
    decision = first.select_next_work(control)
    assert decision.selected_task_id == "PP-STORY-000065"
    assert decision.control_snapshot_id == control.snapshot_id
    assert any(item.startswith("control:") for item in decision.citations)
    recovered = PersistentAutonomyDirector(path)
    status = recovered.recover()
    assert status["recovered"] is True
    assert status["last_selected_task_id"] == "PP-STORY-000065"
    assert status["revision"] == 1
    projection = recovered.projection()
    assert projection["authoritative_for_transitions"] is False
    assert projection["canonical_authority"] == "PROJECT_CONTROL_KERNEL"
    assert projection["chat_mutation"] is False


def test_director_rejects_raw_chat_mutation(tmp_path) -> None:
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    with pytest.raises(AutonomyDirectorError, match="raw chat cannot mutate"):
        director.reject_raw_chat_mutation("please mark REQ-CTRL-0004 done")


def test_director_does_not_invent_work_when_control_has_none(tmp_path) -> None:
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    control = control_snapshot(())
    decision = director.select_next_work(control)
    assert decision.selected_task_id is None
    assert "does not invent" in decision.rationale


def test_director_survives_os_process_exit(tmp_path) -> None:
    state = tmp_path / "director_state.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    writer = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_pipeline.command_center.autonomy_director",
            "select",
            "--state",
            str(state),
            "--ready",
            "PP-STORY-000065",
            "--ready",
            "PP-STORY-000049",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    written = json.loads(writer.stdout)
    assert written["selected_task_id"] == "PP-STORY-000065"
    recover = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_pipeline.command_center.autonomy_director",
            "recover",
            "--state",
            str(state),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    recovered = json.loads(recover.stdout)
    assert recovered["recovered"] is True
    assert recovered["last_selected_task_id"] == "PP-STORY-000065"
    assert recovered["revision"] == 1
    assert recovered["decision_count"] == 1


def test_director_rejects_stale_fingerprint_and_ineligible_selection(tmp_path) -> None:
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    control = control_snapshot(("PP-STORY-000065",))
    with pytest.raises(AutonomyDirectorError, match="stale control fingerprint"):
        director.select_next_work(control, expected_fingerprint="a" * 64)
    denied = control.model_copy(
        update={
            "eligibility": (
                TaskEligibility(
                    task_id="PP-STORY-000065",
                    state="POLICY_DENIED",
                    eligible=False,
                    reasons=("policy denied",),
                ),
            ),
            "readiness": (
                TaskReadiness(
                    task_id="PP-STORY-000065",
                    state="NOT_ELIGIBLE",
                    ready=False,
                    reasons=("policy denied",),
                ),
            ),
        }
    )
    with pytest.raises(AutonomyDirectorError, match="rejected selection"):
        director.select_next_work(denied, requested_task_id="PP-STORY-000065")
    completed = control.model_copy(
        update={
            "eligibility": (
                TaskEligibility(
                    task_id="PP-STORY-000065",
                    state="TERMINAL",
                    eligible=False,
                    reasons=("already complete",),
                ),
            ),
            "readiness": (
                TaskReadiness(
                    task_id="PP-STORY-000065",
                    state="TERMINAL",
                    ready=False,
                    reasons=("already complete",),
                ),
            ),
        }
    )
    assert director.select_next_work(completed).selected_task_id is None
    paused = control.model_copy(
        update={
            "eligibility": (
                TaskEligibility(
                    task_id="PP-STORY-000065",
                    state="PRODUCT_SCOPE_PAUSED",
                    eligible=False,
                    reasons=("paused",),
                ),
            )
        }
    )
    with pytest.raises(AutonomyDirectorError, match="rejected selection"):
        director.select_next_work(paused, requested_task_id="PP-STORY-000065")


def test_director_records_strategy_and_rejects_conflicting_replay(tmp_path) -> None:
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    director.select_next_work(control_snapshot(("PP-STORY-000065",)))
    routed = director.record_strategy(
        goal="close REQ-CTRL-0004",
        plan_steps=("observe", "decide"),
        alternatives=("chat-only",),
        assumptions=("Control remains authority",),
        ambiguity="HIGH_IMPACT_UNRESOLVED",
        risk="HIGH",
        resource_claims=(),
        evidence_citations=("control:live",),
        acceptance_checks=("falsify first-rank-only",),
        rollback_boundary="feat/PP-TASK-000381-director-slice",
    )
    assert routed["status"] == "ROUTED_TO_NEXT_ELIGIBLE"
    accepted = director.record_strategy(
        goal="close REQ-CTRL-0004",
        plan_steps=("observe", "decide", "coordinate"),
        alternatives=("chat-only",),
        assumptions=("Control remains authority",),
        ambiguity="RESOLVED",
        risk="HIGH",
        resource_claims=("director:PP-STORY-000065",),
        evidence_citations=("control:live",),
        acceptance_checks=("persist strategy",),
        rollback_boundary="feat/PP-TASK-000381-director-slice",
    )
    assert accepted["status"] == "ACCEPTED"
    assert accepted["idempotency_key"]
    with pytest.raises(AutonomyDirectorError, match="conflicting strategy replay"):
        director.record_strategy(
            goal="close REQ-CTRL-0004",
            plan_steps=("observe", "decide", "coordinate"),
            alternatives=("chat-only",),
            assumptions=("Control remains authority",),
            ambiguity="RESOLVED",
            risk="HIGH",
            resource_claims=("director:PP-STORY-000065",),
            evidence_citations=("control:live",),
            acceptance_checks=("persist strategy",),
            rollback_boundary="feat/PP-TASK-000381-director-slice",
        )


def test_director_coordinates_fenced_runtime_and_continues_around_blocked_lane(
    tmp_path,
) -> None:
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    director.select_next_work(control_snapshot(("PP-STORY-000065", "PP-STORY-000049")))
    database = tmp_path / "runtime.db"
    first = director.coordinate_execution(
        provider="local",
        root=ROOT,
        database=database,
        blocked_lanes=("PP-STORY-000049",),
    )
    assert first["status"] == "DISPATCHED"
    assert first["operation_id"]
    assert first["context_identity"]
    assert first["leases"]
    assert first["blocked_lanes"] == ["PP-STORY-000049"]
    assert first["continuing_lanes"] == ["PP-STORY-000065"]
    with pytest.raises(AutonomyDirectorError, match="stale fence"):
        director.coordinate_execution(provider="local", root=ROOT, database=database)
    recovered = director.recover_boundary(
        stage="unknown_external_write",
        external_readback="ABSENT",
        retry_authorized=True,
        root=ROOT,
        database=database,
    )
    assert recovered["retry_authorized"] is True
    with pytest.raises(AutonomyDirectorError, match="must be read back"):
        director.recover_boundary(
            stage="unknown_external_write",
            external_readback="UNKNOWN",
            retry_authorized=True,
            root=ROOT,
            database=database,
        )
    with pytest.raises(AutonomyDirectorError, match="not admitted"):
        director.coordinate_execution(
            provider="cursor-cli",
            root=ROOT,
            database=database,
        )
    projection = director.projection()
    assert projection["control_fingerprint"]
    assert projection["typed_controls"]
    assert projection["worker_provider"] == "local"
    assert projection["chat_mutation"] is False


def test_evaluate_live_control_persists_kernel_snapshot(tmp_path) -> None:
    database = tmp_path / "control.db"
    snapshot = evaluate_live_control(ROOT, database_path=database)
    assert snapshot.snapshot_fingerprint
    assert snapshot.sequence.task_count > 0
    with ControlStore(database, ROOT) as store:
        loaded = store.get_snapshot(snapshot.snapshot_id)
    assert loaded is not None
    assert loaded.snapshot_fingerprint == snapshot.snapshot_fingerprint
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    decision = director.select_next_work(snapshot)
    assert "fingerprint:" in "".join(decision.citations)
    assert director.projection()["control_fingerprint"] == snapshot.snapshot_fingerprint
