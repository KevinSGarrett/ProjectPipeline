from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

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
    ResourceClaim,
    ResourcePool,
    ResourceRegistrySnapshot,
    ResourceType,
    SchedulerTaskProfile,
)
from project_pipeline.scheduler.engine import DynamicLaneScheduler

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


def control_snapshot(task_ids):
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
        sequence_id=control_identifier("SEQ", "ortools"),
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
        report_id=control_identifier("SCOPE", "ortools"),
        project_id="PROJECT-PIPELINE",
        requirement_count=0,
        work_item_count=len(items),
        findings=(),
        fingerprint="b" * 64,
        generated_at_utc=NOW,
    )
    completion = CompletionProjection(
        projection_id=control_identifier("COMPLETE", "ortools"),
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
        snapshot_id=control_identifier("CTRL", "ortools"),
        project_id="PROJECT-PIPELINE",
        sequence=seq,
        scope=scope,
        completion=completion,
        eligibility=eligibility,
        readiness=readiness,
        snapshot_fingerprint="c" * 64,
        generated_at_utc=NOW,
    )


def cpu_claim():
    return ResourceClaim(
        resource_key="machine:local/cpu_slots",
        resource_type=ResourceType.CPU_SLOT,
        access_mode=AccessMode.SHARED,
    )


def profile(task_id, rank, utility, *claims):
    return SchedulerTaskProfile(
        task_id=task_id,
        project_id="PROJECT-PIPELINE",
        sequence_rank=rank,
        utility_score=utility,
        priority="P1",
        claims=claims,
    )


def registry(cpu=3, reserve=1):
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


class FakeOptimizer:
    def __init__(self, selected: tuple[str, ...]) -> None:
        self.selected = selected

    def status(self):
        return SimpleNamespace(available=True)

    def select(self, candidates, graph, pools, base_usage, lane_limit):
        return self.selected


def test_scheduler_uses_optional_ortools_optimizer_for_larger_ready_set() -> None:
    task_ids = ("PP-TASK-000001", "PP-TASK-000002", "PP-TASK-000003")
    control = control_snapshot(task_ids)
    profiles = tuple(
        profile(task_id, index, 100 - index, cpu_claim())
        for index, task_id in enumerate(task_ids, 1)
    )
    scheduler = DynamicLaneScheduler(
        exact_candidate_limit=2, ortools_optimizer=FakeOptimizer(task_ids[:2])
    )
    plan = scheduler.plan(control, profiles, registry(cpu=4, reserve=1), now=NOW)
    assert plan.selection_method == "ORTOOLS_CP_SAT"
    assert {lane.task_id for lane in plan.lanes} == set(task_ids[:2])


def test_scheduler_revalidates_optimizer_result_and_falls_back() -> None:
    task_ids = ("PP-TASK-000001", "PP-TASK-000002", "PP-TASK-000003")
    control = control_snapshot(task_ids)
    profiles = tuple(
        profile(task_id, index, 100 - index, cpu_claim())
        for index, task_id in enumerate(task_ids, 1)
    )
    scheduler = DynamicLaneScheduler(
        exact_candidate_limit=2, ortools_optimizer=FakeOptimizer(task_ids)
    )
    plan = scheduler.plan(control, profiles, registry(cpu=2, reserve=1), now=NOW)
    assert plan.selection_method == "DETERMINISTIC_GREEDY"
    assert len(plan.lanes) == 1
