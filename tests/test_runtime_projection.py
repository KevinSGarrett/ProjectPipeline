from __future__ import annotations

from project_pipeline.autonomy_runtime.projection import (
    COMPATIBILITY_HUMAN_REQUIRED,
    LIVE_EXTERNAL_PRECONDITION,
    live_text_is_forbidden,
    project_runtime_state,
    project_status_payload,
)
from project_pipeline.control.graph import BuildSequencer
from project_pipeline.domain.control import EligibilityState, TaskControlFact
from project_pipeline.domain.state import TaskLifecycleState
from project_pipeline.lifecycle.takeover import LaneState


def test_human_required_storage_enum_projects_to_blocked_external() -> None:
    assert LaneState.HUMAN_REQUIRED.value == COMPATIBILITY_HUMAN_REQUIRED
    assert project_runtime_state(LaneState.HUMAN_REQUIRED.value) == LIVE_EXTERNAL_PRECONDITION
    assert project_runtime_state("FAILED") == "FAILED"


def test_status_payload_keeps_stored_enum_and_names_unavailable_capability() -> None:
    projected = project_status_payload(
        {"state": "HUMAN_REQUIRED", "reason": "cursor-cli executable unavailable"}
    )
    assert projected["state"] == "BLOCKED_EXTERNAL"
    assert projected["stored_state"] == "HUMAN_REQUIRED"
    assert projected["unavailable_capability"] == "cursor-cli executable unavailable"
    assert not live_text_is_forbidden(projected["state"])


def test_live_projection_forbids_operator_assignment_phrases() -> None:
    assert live_text_is_forbidden("await human to merge")
    assert live_text_is_forbidden("HUMAN_REQUIRED")
    assert not live_text_is_forbidden("BLOCKED_EXTERNAL")


def test_control_human_required_eligibility_keeps_storage_enum_without_human_assignment() -> None:
    fact = TaskControlFact(
        task_id="PP-TASK-000001",
        project_id="PROJECT-PIPELINE",
        state=TaskLifecycleState.BACKLOG,
        issue_type="TASK",
        priority="P1",
        risk="MEDIUM",
        human_required=True,
    )
    eligibility = BuildSequencer((fact,)).eligibility(fact)
    assert eligibility.state is EligibilityState.HUMAN_REQUIRED
    joined = " ".join(eligibility.reasons)
    assert "external precondition" in joined
    assert "human decision" not in joined
    assert "human action" not in joined
