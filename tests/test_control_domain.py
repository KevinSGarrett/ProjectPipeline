from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from project_pipeline.domain.control import (
    CompletionProjection,
    CompletionProjectionState,
    EligibilityState,
    ReadinessState,
    SequenceScore,
    TaskControlFact,
    TaskEligibility,
    TaskReadiness,
    control_identifier,
)
from project_pipeline.domain.state import TaskLifecycleState


def test_control_identifier_is_deterministic_and_scoped() -> None:
    first = control_identifier("CTRL", "PROJECT-PIPELINE", "abc")
    second = control_identifier("CTRL", "PROJECT-PIPELINE", "abc")
    other = control_identifier("SEQ", "PROJECT-PIPELINE", "abc")
    assert first == second
    assert first.startswith("CTRL-")
    assert other.startswith("SEQ-")
    assert first != other


def test_task_control_fact_rejects_naive_deadline() -> None:
    with pytest.raises(ValidationError):
        TaskControlFact(
            task_id="PP-TASK-000001",
            project_id="PROJECT-PIPELINE",
            state=TaskLifecycleState.BACKLOG,
            issue_type="TASK",
            priority="P1",
            risk="MEDIUM",
            deadline_utc=datetime(2026, 8, 15, 12, 0),
        )


def test_task_control_fact_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError):
        TaskControlFact(
            task_id="PP-TASK-000001",
            project_id="PROJECT-PIPELINE",
            state=TaskLifecycleState.BACKLOG,
            issue_type="TASK",
            priority="P1",
            risk="MEDIUM",
            dependency_ids=("PP-TASK-000001",),
        )


def test_eligibility_and_readiness_booleans_must_match_state() -> None:
    with pytest.raises(ValidationError):
        TaskEligibility(
            task_id="PP-TASK-000001",
            state=EligibilityState.ELIGIBLE,
            eligible=False,
            reasons=("bad",),
        )
    with pytest.raises(ValidationError):
        TaskReadiness(
            task_id="PP-TASK-000001",
            state=ReadinessState.READY,
            ready=False,
            reasons=("bad",),
        )


def test_sequence_score_requires_exact_component_sum() -> None:
    with pytest.raises(ValidationError):
        SequenceScore(
            task_id="PP-TASK-000001",
            priority_score=100,
            critical_path_score=0,
            deadline_score=0,
            risk_score=0,
            unblock_score=0,
            duration_score=0,
            total_score=99,
        )


def test_completion_projection_cannot_self_satisfy_final_gate() -> None:
    with pytest.raises(ValidationError):
        CompletionProjection(
            projection_id=control_identifier("COMPLETE", "PROJECT-PIPELINE", "x"),
            project_id="PROJECT-PIPELINE",
            state=CompletionProjectionState.READY_FOR_COMPLETION_GATE,
            total_work_items=1,
            completed_work_items=1,
            active_work_items=0,
            blocked_work_items=0,
            failed_work_items=0,
            accepted_requirements=1,
            implemented_or_external_blocked_requirements=1,
            ready_work_items=0,
            verification_eligible=True,
            final_completion_gate_satisfied=True,
            reasons=("bad authority",),
            generated_at_utc=datetime.now(UTC),
        )
