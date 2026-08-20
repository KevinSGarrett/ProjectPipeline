from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.domain.control import ReadinessState, TaskReadiness
from project_pipeline.domain.scheduler import ResourceClaim, ResourceType, SchedulerTaskProfile
from project_pipeline.scheduler import DynamicLaneScheduler
from project_pipeline.scheduler.productive_idle import (
    apply_productive_idle_progress,
    evaluate_productive_idle,
)
from tests.test_scheduler_engine import control_snapshot, cpu_claim, profile, registry

NOW = datetime(2026, 8, 19, tzinfo=UTC)


def _waiting_control() -> object:
    control = control_snapshot(("PP-TASK-000002",))
    readiness = (
        TaskReadiness(
            task_id="PP-TASK-000001",
            state=ReadinessState.WAITING_DEPENDENCIES,
            ready=False,
            unresolved_dependencies=("PP-TASK-000099",),
            reasons=("waiting on dependency",),
        ),
        TaskReadiness(task_id="PP-TASK-000002", state=ReadinessState.READY, ready=True),
    )
    return control.model_copy(update={"readiness": readiness})


def test_productive_idle_selects_and_progresses_unrelated_ready_lane(tmp_path: Path) -> None:
    control = _waiting_control()
    waiting_profile = SchedulerTaskProfile(
        task_id="PP-TASK-000001",
        project_id="PROJECT-PIPELINE",
        sequence_rank=1,
        utility_score=200,
        priority="P0",
        critical_path=True,
        claims=(ResourceClaim(resource_key="src/critical", resource_type=ResourceType.PATH),),
    )
    idle = profile(
        "PP-TASK-000002",
        2,
        80,
        cpu_claim(),
        ResourceClaim(resource_key="src/docs", resource_type=ResourceType.PATH),
    ).model_copy(update={"productive_idle": True})
    plan = DynamicLaneScheduler().plan(control, (idle,), registry(cpu=3, reserve=1), now=NOW)
    decision = evaluate_productive_idle(
        control,
        plan,
        (waiting_profile, idle),
        waiting_claims={"PP-TASK-000001": waiting_profile.claims},
    )
    progressed = apply_productive_idle_progress(decision, tmp_path / "idle", now=NOW)
    again = apply_productive_idle_progress(decision, tmp_path / "idle", now=NOW)
    assert progressed.progressed is True
    assert progressed.selected_task_id == "PP-TASK-000002"
    assert progressed.progress_count == 1
    assert again.progress_count == 2
    assert progressed.receipt_path
    assert Path(progressed.receipt_path).is_file()


def test_productive_idle_rejects_protected_capacity_and_shared_scope() -> None:
    control = _waiting_control()
    waiting_claims = (ResourceClaim(resource_key="src/shared", resource_type=ResourceType.PATH),)
    protected = profile("PP-TASK-000002", 2, 80, cpu_claim()).model_copy(
        update={"protected_capacity_consumption": True, "productive_idle": True}
    )
    overlapping = profile(
        "PP-TASK-000002",
        2,
        80,
        ResourceClaim(resource_key="src/shared/module", resource_type=ResourceType.PATH),
    )
    plan = DynamicLaneScheduler().plan(control, (protected,), registry(cpu=3, reserve=1), now=NOW)
    blocked_capacity = evaluate_productive_idle(
        control, plan, (protected,), waiting_claims={"PP-TASK-000001": waiting_claims}
    )
    overlap_plan = DynamicLaneScheduler().plan(
        control, (overlapping,), registry(cpu=3, reserve=1), now=NOW
    )
    blocked_scope = evaluate_productive_idle(
        control,
        overlap_plan,
        (overlapping,),
        waiting_claims={"PP-TASK-000001": waiting_claims},
    )
    assert blocked_capacity.progressed is False
    assert blocked_capacity.selected_task_id is None
    assert any(item.startswith("protected_capacity:") for item in blocked_capacity.reasons)
    assert blocked_scope.selected_task_id is None
    assert any(item.startswith("shared_scope:") for item in blocked_scope.reasons)
