from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from project_pipeline.control import BuildSequencer, ControlGraphError
from project_pipeline.domain.control import EligibilityState, ReadinessState, TaskControlFact
from project_pipeline.domain.state import TaskLifecycleState


def fact(
    task_id: str,
    *,
    state: TaskLifecycleState = TaskLifecycleState.BACKLOG,
    deps: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
    priority: str = "P1",
    risk: str = "MEDIUM",
    duration: int | None = None,
    deadline=None,
    issue_type: str = "TASK",
    **overrides,
) -> TaskControlFact:
    return TaskControlFact(
        task_id=task_id,
        project_id="PROJECT-PIPELINE",
        state=state,
        issue_type=issue_type,
        priority=priority,
        risk=risk,
        dependency_ids=deps,
        blocker_ids=blockers,
        expected_duration_minutes=duration,
        deadline_utc=deadline,
        **overrides,
    )


def test_unknown_dependency_fails_closed() -> None:
    with pytest.raises(ControlGraphError, match="unknown work item"):
        BuildSequencer((fact("PP-TASK-000001", deps=("PP-TASK-000002",)),))


def test_cycle_fails_closed() -> None:
    with pytest.raises(ControlGraphError, match="cycle"):
        BuildSequencer(
            (
                fact("PP-TASK-000001", deps=("PP-TASK-000002",)),
                fact("PP-TASK-000002", deps=("PP-TASK-000001",)),
            )
        )


def test_structural_epic_is_not_executable() -> None:
    seq = BuildSequencer((fact("PP-EPIC-000001", issue_type="EPIC"),))
    result = seq.eligibility(seq.facts[0])
    assert result.state is EligibilityState.POLICY_DENIED
    assert not result.eligible


def test_dependency_completion_controls_readiness() -> None:
    a = fact("PP-TASK-000001", state=TaskLifecycleState.DONE)
    b = fact("PP-TASK-000002", deps=(a.task_id,))
    seq = BuildSequencer((a, b))
    assert seq.readiness(b).state is ReadinessState.READY
    waiting = BuildSequencer((a.model_copy(update={"state": TaskLifecycleState.BACKLOG}), b))
    result = waiting.readiness(b)
    assert result.state is ReadinessState.WAITING_DEPENDENCIES
    assert result.unresolved_dependencies == (a.task_id,)


def test_blocked_work_does_not_stop_independent_work() -> None:
    blocked = fact("PP-TASK-000001", state=TaskLifecycleState.BLOCKED)
    independent = fact("PP-TASK-000002")
    seq = BuildSequencer((blocked, independent))
    assert not seq.readiness(blocked).ready
    assert seq.readiness(independent).ready
    built = seq.build_sequence()
    assert [item.task_id for item in built.ordered_ready_work] == [independent.task_id]


def test_approval_context_resource_and_environment_predicates() -> None:
    cases = [
        ({"approval_required": True, "approval_satisfied": False}, ReadinessState.WAITING_APPROVAL),
        ({"context_required": True, "context_satisfied": False}, ReadinessState.WAITING_CONTEXT),
        ({"resources_available": False}, ReadinessState.WAITING_RESOURCES),
        ({"environment_available": False}, ReadinessState.WAITING_ENVIRONMENT),
    ]
    for index, (overrides, expected) in enumerate(cases, start=1):
        item = fact(f"PP-TASK-{index:06d}", **overrides)
        assert BuildSequencer((item,)).readiness(item).state is expected


def test_external_blocks_are_ineligible_and_autonomously_owned() -> None:
    external = fact("PP-TASK-000001", external_blocked=True)
    seq = BuildSequencer((external,))
    assert seq.eligibility(external).state is EligibilityState.BLOCKED_EXTERNAL
    assert "autonomous recovery" in " ".join(seq.eligibility(external).reasons)


def test_declared_duration_critical_path_is_deterministic() -> None:
    a = fact("PP-TASK-000001", duration=10)
    b = fact("PP-TASK-000002", deps=(a.task_id,), duration=30)
    c = fact("PP-TASK-000003", duration=25)
    d = fact("PP-TASK-000004", deps=(c.task_id,), duration=5)
    seq = BuildSequencer((a, b, c, d))
    cp = seq.critical_path()
    assert cp.path == (a.task_id, b.task_id)
    assert cp.total_duration_minutes == 40
    assert cp.duration_source == "DECLARED"
    assert cp.slack_minutes[b.task_id] == 0


def test_completed_work_has_zero_remaining_duration() -> None:
    done = fact("PP-TASK-000001", state=TaskLifecycleState.DONE, duration=500)
    remaining = fact("PP-TASK-000002", deps=(done.task_id,), duration=30)
    cp = BuildSequencer((done, remaining)).critical_path()
    assert cp.total_duration_minutes == 30
    assert cp.path[-1] == remaining.task_id


def test_default_duration_is_explicitly_heuristic() -> None:
    seq = BuildSequencer((fact("PP-TASK-000001"), fact("PP-TASK-000002")))
    assert seq.critical_path().duration_source == "DEFAULT_HEURISTIC"


def test_priority_score_considers_priority_criticality_deadline_risk_and_unblock() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    high = fact(
        "PP-TASK-000001",
        priority="P0",
        risk="CRITICAL",
        deadline=now + timedelta(hours=2),
    )
    child = fact("PP-TASK-000002", deps=(high.task_id,), state=TaskLifecycleState.BACKLOG)
    low = fact("PP-TASK-000003", priority="P3", risk="LOW")
    built = BuildSequencer((high, child, low)).build_sequence(now=now)
    assert built.ordered_ready_work[0].task_id == high.task_id
    score = built.ordered_ready_work[0].score
    assert score.priority_score == 1000
    assert score.deadline_score == 150
    assert score.risk_score == 40
    assert score.unblock_score > 0


def test_ties_break_by_stable_task_identifier() -> None:
    a = fact("PP-TASK-000002")
    b = fact("PP-TASK-000001")
    order = [item.task_id for item in BuildSequencer((a, b)).build_sequence().ordered_ready_work]
    assert order == ["PP-TASK-000001", "PP-TASK-000002"]


def test_graph_fingerprint_changes_after_accepted_state_change() -> None:
    a = fact("PP-TASK-000001")
    first = BuildSequencer((a,)).graph_fingerprint()
    second = BuildSequencer(
        (a.model_copy(update={"state": TaskLifecycleState.DONE}),)
    ).graph_fingerprint()
    assert first != second
