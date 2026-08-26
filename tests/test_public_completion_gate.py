from project_pipeline.assurance.completion import (
    assess_candidate_completion,
    evaluate_completion_gate,
)
from project_pipeline.domain.assurance import (
    CandidateCompletionState,
    CompletionGateFacts,
    FailureCategory,
    GateState,
)


def facts(**overrides: object) -> CompletionGateFacts:
    data: dict[str, object] = {
        "project_id": "PROJECT-PIPELINE",
        "source_requirements_dispositioned": True,
        "accepted_requirements_complete_or_external": True,
        "implementation_traceability_complete": True,
        "critical_paths_tested": True,
        "golden_journeys_pass": True,
        "autonomous_runtime_qualified": True,
        "security_gates_satisfied": True,
        "resilience_verified": True,
        "deployment_reproducible": True,
        "rollback_verified": True,
        "engineer_operable_from_docs": True,
        "ai_continuable_from_repo_and_jira": True,
        "unresolved_items_truthful": True,
        "command_center_truthful": True,
        "jira_truthful": True,
        "unattended_operating_loop_qualified": True,
        "unexplained_gap_count": 0,
        "snapshot_fingerprint": "a" * 64,
    }
    data.update(overrides)
    return CompletionGateFacts(**data)


def test_candidate_claim_is_challenged_by_missing_or_stale_evidence() -> None:
    result = assess_candidate_completion(
        work_item_id="PP-TASK-X",
        implementer_id="agent",
        criteria_total=3,
        criteria_passing=2,
        stale_evidence_count=1,
        unknown_count=1,
        independent_review_required=True,
        independent_review_satisfied=False,
    )

    assert result.state is CandidateCompletionState.CHALLENGE
    assert len(result.reasons) >= 3


def test_candidate_ready_still_requires_the_final_completion_gate() -> None:
    result = assess_candidate_completion(
        work_item_id="PP-TASK-X",
        implementer_id="agent",
        criteria_total=2,
        criteria_passing=2,
        stale_evidence_count=0,
        unknown_count=0,
        independent_review_required=False,
        independent_review_satisfied=False,
    )

    assert result.state is CandidateCompletionState.READY_FOR_COMPLETION_GATE
    assert any("final Completion Gate" in reason for reason in result.reasons)


def test_complete_requires_all_completion_facts() -> None:
    decision = evaluate_completion_gate(facts())

    assert decision.state is GateState.COMPLETE
    assert decision.final_complete is True
    assert len(decision.questions) == 16
    assert not decision.failures


def test_single_failure_prevents_completion_and_localizes_rework() -> None:
    decision = evaluate_completion_gate(facts(golden_journeys_pass=False))

    assert decision.state is GateState.NOT_COMPLETE
    assert decision.final_complete is False
    assert decision.failures[0].category is FailureCategory.GOLDEN_JOURNEY
    assert decision.failures[0].rework_route == "completion.question.5"


def test_only_external_blockers_are_not_completion() -> None:
    decision = evaluate_completion_gate(
        facts(deployment_reproducible=False, externally_blocked_question_numbers=(8,))
    )

    assert decision.state is GateState.BLOCKED_EXTERNAL
    assert decision.final_complete is False
