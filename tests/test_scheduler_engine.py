from __future__ import annotations

from datetime import UTC, datetime

from project_pipeline.domain.control import (
    BuildSequence,
    CompletionProjection,
    CompletionProjectionState,
    ControlSnapshot,
    CriticalPathAnalysis,
    ReadinessState,
    ScopeReconciliationReport,
    SequenceItem,
    SequenceScore,
    TaskEligibility,
    TaskReadiness,
    control_identifier,
)
from project_pipeline.domain.scheduler import (
    AccessMode,
    BackpressureSignals,
    ResourceClaim,
    ResourcePool,
    ResourceRegistrySnapshot,
    ResourceType,
    SchedulerTaskProfile,
)
from project_pipeline.scheduler import DynamicLaneScheduler

NOW = datetime(2026, 8, 15, tzinfo=UTC)


def score(task_id: str, total: int) -> SequenceScore:
    return SequenceScore(
        task_id=task_id,
        priority_score=total,
        critical_path_score=0,
        deadline_score=0,
        risk_score=0,
        unblock_score=0,
        duration_score=0,
        total_score=total,
    )


def control_snapshot(
    task_ids=("PP-TASK-000001", "PP-TASK-000002", "PP-TASK-000003"),
) -> ControlSnapshot:
    items = tuple(
        SequenceItem(
            rank=i,
            task_id=t,
            readiness=ReadinessState.READY,
            score=score(t, 100 - i),
            dependency_depth=0,
            downstream_count=0,
            on_critical_path=(i == 1),
        )
        for i, t in enumerate(task_ids, 1)
    )
    seq = BuildSequence(
        sequence_id=control_identifier("SEQ", "test"),
        project_id="PROJECT-PIPELINE",
        graph_fingerprint="a" * 64,
        task_count=len(items),
        edge_count=0,
        ready_count=len(items),
        active_count=0,
        blocked_count=0,
        critical_path=CriticalPathAnalysis(
            path=(),
            total_duration_minutes=0,
            duration_source="EMPTY",
            earliest_finish_minutes={},
            slack_minutes={},
        ),
        ordered_ready_work=items,
        generated_at_utc=NOW,
    )
    scope = ScopeReconciliationReport(
        report_id=control_identifier("SCOPE", "test"),
        project_id="PROJECT-PIPELINE",
        requirement_count=0,
        work_item_count=len(items),
        findings=(),
        fingerprint="b" * 64,
        generated_at_utc=NOW,
    )
    completion = CompletionProjection(
        projection_id=control_identifier("COMPLETE", "test"),
        project_id="PROJECT-PIPELINE",
        state=CompletionProjectionState.INCOMPLETE,
        total_work_items=len(items),
        completed_work_items=0,
        active_work_items=0,
        blocked_work_items=0,
        failed_work_items=0,
        accepted_requirements=0,
        implemented_or_external_blocked_requirements=0,
        ready_work_items=len(items),
        verification_eligible=False,
        reasons=("work remains",),
        generated_at_utc=NOW,
    )
    eligibility = tuple(
        TaskEligibility(task_id=t, state="ELIGIBLE", eligible=True) for t in task_ids
    )
    readiness = tuple(TaskReadiness(task_id=t, state="READY", ready=True) for t in task_ids)
    return ControlSnapshot(
        snapshot_id=control_identifier("CTRL", "test"),
        project_id="PROJECT-PIPELINE",
        sequence=seq,
        scope=scope,
        completion=completion,
        eligibility=eligibility,
        readiness=readiness,
        snapshot_fingerprint="c" * 64,
        generated_at_utc=NOW,
    )


def profile(task_id: str, rank: int, utility: int, *claims: ResourceClaim) -> SchedulerTaskProfile:
    return SchedulerTaskProfile(
        task_id=task_id,
        project_id="PROJECT-PIPELINE",
        sequence_rank=rank,
        utility_score=utility,
        priority="P1",
        claims=claims,
    )


def registry(cpu=3, reserve=1) -> ResourceRegistrySnapshot:
    return ResourceRegistrySnapshot.create(
        pools=(
            ResourcePool(
                resource_key="machine:local/cpu_slots",
                resource_type=ResourceType.CPU_SLOT,
                capacity_units=cpu,
                reserved_units=reserve,
            ),
        ),
        observed_at_utc=NOW,
    )


def cpu_claim() -> ResourceClaim:
    return ResourceClaim(
        resource_key="machine:local/cpu_slots",
        resource_type=ResourceType.CPU_SLOT,
        access_mode=AccessMode.SHARED,
    )


def test_scheduler_selects_safe_parallel_set_under_capacity() -> None:
    control = control_snapshot()
    profiles = (
        profile("PP-TASK-000001", 1, 100, cpu_claim()),
        profile("PP-TASK-000002", 2, 90, cpu_claim()),
        profile("PP-TASK-000003", 3, 80, cpu_claim()),
    )
    plan = DynamicLaneScheduler().plan(control, profiles, registry(cpu=3, reserve=1), now=NOW)
    assert [x.task_id for x in plan.lanes] == ["PP-TASK-000001", "PP-TASK-000002"]
    assert len(plan.lanes) == 2


def test_scheduler_prefers_higher_total_utility_when_conflicts_exist() -> None:
    control = control_snapshot()
    shared = ResourceClaim(resource_key="src/auth", resource_type=ResourceType.PATH)
    profiles = (
        profile("PP-TASK-000001", 1, 100, shared),
        profile("PP-TASK-000002", 2, 200, shared),
        profile(
            "PP-TASK-000003",
            3,
            50,
            ResourceClaim(resource_key="src/docs", resource_type=ResourceType.PATH),
        ),
    )
    plan = DynamicLaneScheduler().plan(
        control, profiles, ResourceRegistrySnapshot.create(pools=(), observed_at_utc=NOW), now=NOW
    )
    assert {x.task_id for x in plan.lanes} == {"PP-TASK-000002", "PP-TASK-000003"}


def test_brownout_pauses_new_work_without_cancelling_state() -> None:
    control = control_snapshot()
    profiles = tuple(
        profile(t, i, 100, cpu_claim())
        for i, t in enumerate(("PP-TASK-000001", "PP-TASK-000002", "PP-TASK-000003"), 1)
    )
    plan = DynamicLaneScheduler().plan(
        control, profiles, registry(), signals=BackpressureSignals(queue_depth=200), now=NOW
    )
    assert plan.backpressure.mode.value == "BROWNOUT"
    assert not plan.lanes
    assert all(not item.admitted for item in plan.admissions)


def test_congested_mode_reduces_lane_limit() -> None:
    control = control_snapshot()
    profiles = tuple(
        profile(t, i, 100, cpu_claim())
        for i, t in enumerate(("PP-TASK-000001", "PP-TASK-000002", "PP-TASK-000003"), 1)
    )
    plan = DynamicLaneScheduler().plan(
        control,
        profiles,
        registry(cpu=10, reserve=1),
        signals=BackpressureSignals(queue_depth=50),
        max_lanes=3,
        now=NOW,
    )
    assert plan.backpressure.mode.value == "CONGESTED"
    assert plan.lane_limit == 1
    assert len(plan.lanes) == 1


def test_scheduler_is_deterministic_for_same_semantic_inputs() -> None:
    control = control_snapshot()
    profiles = (
        profile("PP-TASK-000001", 1, 100, cpu_claim()),
        profile("PP-TASK-000002", 2, 90, cpu_claim()),
        profile("PP-TASK-000003", 3, 80, cpu_claim()),
    )
    first = DynamicLaneScheduler().plan(control, profiles, registry(cpu=4, reserve=1), now=NOW)
    second = DynamicLaneScheduler().plan(control, profiles, registry(cpu=4, reserve=1), now=NOW)
    assert first.plan_id == second.plan_id
    assert first.lanes == second.lanes
