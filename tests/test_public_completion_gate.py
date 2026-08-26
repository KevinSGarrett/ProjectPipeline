from project_pipeline.assurance.completion import (
    _evidence_matches_current_identity,
    _evidence_rows,
    _question_five_reason,
    _valid_unattended_qualification,
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


def test_runtime_qualification_reason_identifies_each_failed_binding() -> None:
    reason = _question_five_reason(
        autonomous_runtime_qualified=False,
        missing_runtime_environments=["unattended_72_hour"],
        ancestor_blocked=True,
        compiler_unbound=True,
    )

    assert "ancestor_or_different_head_receipt" in reason
    assert "current_sha_tree_binding_missing" in reason
    assert "unattended_72_hour" in reason


def test_runtime_qualification_reason_handles_verified_and_generic_incomplete_states() -> None:
    assert "verified evidence" in _question_five_reason(
        autonomous_runtime_qualified=True,
        missing_runtime_environments=[],
        ancestor_blocked=False,
        compiler_unbound=False,
    )
    assert "qualification is incomplete" in _question_five_reason(
        autonomous_runtime_qualified=False,
        missing_runtime_environments=[],
        ancestor_blocked=False,
        compiler_unbound=False,
    )


def test_runtime_evidence_must_be_a_bound_json_file_under_the_checkout(tmp_path) -> None:
    sha = "a" * 40
    tree = "b" * 40
    artifact = tmp_path / "evidence" / "runtime.json"
    artifact.parent.mkdir()
    artifact.write_text(
        '{"bound_head": "' + sha + '", "bound_tree": "' + tree + '"}', encoding="utf-8"
    )
    row = {
        "environment": "unattended_72_hour",
        "artifact_path": "evidence/runtime.json",
    }

    assert _evidence_matches_current_identity(tmp_path, row, sha, tree)
    assert not _evidence_matches_current_identity(tmp_path, row, sha, "c" * 40)
    assert not _evidence_matches_current_identity(
        tmp_path,
        {"environment": "unattended_72_hour", "artifact_path": "../outside.json"},
        sha,
        tree,
    )


def test_runtime_evidence_rejects_missing_non_json_and_malformed_receipts(tmp_path) -> None:
    sha = "a" * 40
    tree = "b" * 40
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "runtime.txt").write_text("not json", encoding="utf-8")
    (evidence_dir / "malformed.json").write_text("not json", encoding="utf-8")

    assert _evidence_matches_current_identity(tmp_path, {"environment": "unit"}, sha, tree)
    assert not _evidence_matches_current_identity(
        tmp_path, {"environment": "unattended_72_hour"}, sha, tree
    )
    assert not _evidence_matches_current_identity(
        tmp_path,
        {"environment": "unattended_72_hour", "artifact_path": "evidence/runtime.txt"},
        sha,
        tree,
    )
    assert not _evidence_matches_current_identity(
        tmp_path,
        {"environment": "unattended_72_hour", "artifact_path": "evidence/malformed.json"},
        sha,
        tree,
    )


def test_evidence_ledger_reader_ignores_empty_lines(tmp_path) -> None:
    evidence = tmp_path / "evidence" / "EVIDENCE_LEDGER.jsonl"
    evidence.parent.mkdir()
    evidence.write_text('{"evidence_id": "EVID-1"}\n\n', encoding="utf-8")

    assert _evidence_rows(tmp_path) == ({"evidence_id": "EVID-1"},)


def test_unattended_qualification_requires_complete_72_hour_receipt(tmp_path) -> None:
    artifact = tmp_path / "evidence" / "qualification.json"
    artifact.parent.mkdir()
    artifact.write_text(
        """{
  "duration_hours": 72,
  "end_to_end": true,
  "restart_recovery": true,
  "external_reconciliation": true,
  "windows_native_verified": true,
  "unattended": true
}""",
        encoding="utf-8",
    )
    row = {"artifact_path": "evidence/qualification.json"}

    assert _valid_unattended_qualification(tmp_path, row)
    assert not _valid_unattended_qualification(tmp_path, {"artifact_path": "missing.json"})


def test_unattended_qualification_rejects_missing_and_malformed_receipts(tmp_path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "receipt.txt").write_text("not json", encoding="utf-8")
    (evidence_dir / "malformed.json").write_text("not json", encoding="utf-8")

    assert not _valid_unattended_qualification(tmp_path, {})
    assert not _valid_unattended_qualification(tmp_path, {"artifact_path": "../outside.json"})
    assert not _valid_unattended_qualification(tmp_path, {"artifact_path": "evidence/receipt.txt"})
    assert not _valid_unattended_qualification(
        tmp_path, {"artifact_path": "evidence/malformed.json"}
    )
