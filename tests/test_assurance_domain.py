from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from project_pipeline.domain.assurance import (
    AcceptanceCriterion,
    AssuranceRisk,
    CandidateCompletionAssessment,
    CandidateCompletionState,
    CompletionGateDecision,
    CompletionQuestionResult,
    GateState,
    ReviewerIdentity,
    TruthKind,
    TruthRecord,
    VerificationMethod,
    assurance_fingerprint,
    assurance_identifier,
)

NOW = datetime(2026, 8, 15, 18, tzinfo=UTC)


def criterion(risk: AssuranceRisk = AssuranceRisk.MEDIUM) -> AcceptanceCriterion:
    fp = assurance_fingerprint(
        {"work": "PP-TASK-1", "statement": "Behavior is objectively verified"}
    )
    statement = "Behavior is objectively verified"
    return AcceptanceCriterion(
        criterion_id=assurance_identifier("CRIT", "PP-TASK-1", statement, fp),
        work_item_id="PP-TASK-1",
        statement=statement,
        risk=risk,
        verification_methods=(VerificationMethod.UNIT,),
        frozen_fingerprint=fp,
    )


def test_assurance_identifier_is_stable_and_namespaced():
    assert assurance_identifier("GATE", "PROJECT-PIPELINE", "snapshot") == assurance_identifier(
        "GATE", "PROJECT-PIPELINE", "snapshot"
    )
    assert assurance_identifier("GATE", "PROJECT-PIPELINE", "snapshot").startswith("GATE-")


def test_acceptance_criterion_rejects_identity_drift():
    base = criterion().model_dump()
    base["criterion_id"] = assurance_identifier("CRIT", "different", "semantics")
    with pytest.raises(ValidationError):
        AcceptanceCriterion(**base)


def test_verified_fact_requires_evidence():
    with pytest.raises(ValidationError):
        TruthRecord(
            truth_id=assurance_identifier("TRUTH", "subject", "fact"),
            subject_id="subject",
            kind=TruthKind.VERIFIED_FACT,
            statement="verified",
            verification_status="VERIFIED",
            observed_at_utc=NOW,
        )


def test_unknown_truth_cannot_carry_evidence():
    with pytest.raises(ValidationError):
        TruthRecord(
            truth_id=assurance_identifier("TRUTH", "subject", "unknown"),
            subject_id="subject",
            kind=TruthKind.UNKNOWN,
            statement="unknown",
            evidence_ids=("EVID-000001",),
            observed_at_utc=NOW,
        )


def test_reviewer_independence_requires_identity_and_context_separation():
    independent = ReviewerIdentity(
        reviewer_id="reviewer-a",
        implementer_id="implementer-b",
        context_fingerprint="a" * 64,
        implementation_context_fingerprint="b" * 64,
    )
    same_context = independent.model_copy(update={"context_fingerprint": "b" * 64})
    conflicted = independent.model_copy(update={"conflicts": ("same-team-review-owner",)})
    assert independent.independent is True
    assert same_context.independent is False
    assert conflicted.independent is False


def test_completion_gate_model_rejects_false_complete_claim():
    question = CompletionQuestionResult(
        question_number=1, question="q", passed=False, reasons=("missing",)
    )
    with pytest.raises(ValidationError):
        CompletionGateDecision(
            gate_id=assurance_identifier("GATE", "PROJECT-PIPELINE", "x"),
            project_id="PROJECT-PIPELINE",
            state=GateState.COMPLETE,
            questions=(question,),
            failures=(),
            source_snapshot_fingerprint="a" * 64,
            final_complete=True,
        )


def test_candidate_completion_cannot_report_more_passing_than_total():
    with pytest.raises(ValidationError):
        CandidateCompletionAssessment(
            assessment_id=assurance_identifier("CAND", "PP-TASK-1", "bad"),
            work_item_id="PP-TASK-1",
            state=CandidateCompletionState.CHALLENGE,
            implementer_id="agent",
            criteria_total=1,
            criteria_passing=2,
            stale_evidence_count=0,
            unknown_count=0,
            independent_review_required=False,
            independent_review_satisfied=False,
            reasons=("invalid",),
        )
