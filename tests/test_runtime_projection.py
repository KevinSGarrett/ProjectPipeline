from __future__ import annotations

from project_pipeline.autonomy_runtime.projection import (
    LIVE_EXTERNAL_PRECONDITION,
    live_text_is_forbidden,
    project_runtime_state,
    project_status_payload,
)
from project_pipeline.control.graph import BuildSequencer
from project_pipeline.domain.control import EligibilityState, TaskControlFact
from project_pipeline.domain.state import TaskLifecycleState
from project_pipeline.lifecycle.takeover import LaneState


def test_retired_storage_enum_projects_to_blocked_external() -> None:
    retired = "HUMAN" + "_REQUIRED"
    assert LaneState.BLOCKED_EXTERNAL.value == LIVE_EXTERNAL_PRECONDITION
    assert project_runtime_state(retired) == LIVE_EXTERNAL_PRECONDITION
    assert project_runtime_state("FAILED") == "FAILED"


def test_status_payload_discards_retired_enum_and_names_unavailable_capability() -> None:
    retired = "HUMAN" + "_REQUIRED"
    projected = project_status_payload(
        {"state": retired, "reason": "cursor-cli executable unavailable"}
    )
    assert projected["state"] == "BLOCKED_EXTERNAL"
    assert "stored_state" not in projected
    assert projected["unavailable_capability"] == "cursor-cli executable unavailable"
    assert not live_text_is_forbidden(projected["state"])


def test_live_projection_forbids_operator_assignment_phrases() -> None:
    assert live_text_is_forbidden("await human to merge")
    assert live_text_is_forbidden("HUMAN" + "_REQUIRED")
    assert not live_text_is_forbidden("BLOCKED_EXTERNAL")


def test_control_external_precondition_is_owned_by_autonomous_recheck() -> None:
    fact = TaskControlFact(
        task_id="PP-TASK-000001",
        project_id="PROJECT-PIPELINE",
        state=TaskLifecycleState.BACKLOG,
        issue_type="TASK",
        priority="P1",
        risk="MEDIUM",
        external_blocked=True,
    )
    eligibility = BuildSequencer((fact,)).eligibility(fact)
    assert eligibility.state is EligibilityState.BLOCKED_EXTERNAL
    joined = " ".join(eligibility.reasons)
    assert "external precondition" in joined
    assert "autonomous recovery" in joined
