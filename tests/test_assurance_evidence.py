from datetime import UTC, datetime, timedelta

from project_pipeline.assurance.evidence import (
    assess_evidence_for_criterion,
    evidence_sufficient,
    truth_from_claim,
    verified_fact,
)
from project_pipeline.domain.assurance import (
    AcceptanceCriterion,
    AssuranceRisk,
    CriterionState,
    IndependentReview,
    ReviewerIdentity,
    TruthKind,
    VerificationMethod,
    assurance_fingerprint,
    assurance_identifier,
)

NOW = datetime(2026, 8, 15, 18, tzinfo=UTC)


def criterion(risk=AssuranceRisk.MEDIUM):
    statement = "The acceptance criterion has fresh evidence."
    fp = assurance_fingerprint((statement, risk.value))
    return AcceptanceCriterion(
        criterion_id=assurance_identifier("CRIT", "PP-TASK-X", statement, fp),
        work_item_id="PP-TASK-X",
        statement=statement,
        risk=risk,
        verification_methods=(VerificationMethod.UNIT, VerificationMethod.INTEGRATION),
        frozen_fingerprint=fp,
    )


def record(
    c, evidence_id, *, result="PASS", verified="VERIFIED", age_days=0, method="pytest unit tests"
):
    return {
        "evidence_id": evidence_id,
        "criterion_ids": [c.criterion_id],
        "verification_status": verified,
        "result": result,
        "observed_at_utc": (NOW - timedelta(days=age_days)).isoformat(),
        "method": method,
        "claim": "criterion evidence",
        "artifact_path": "evidence/test.txt",
        "environment": "independent-verifier",
    }


def review(c, *, independent=True, blockers=0):
    identity = ReviewerIdentity(
        reviewer_id="reviewer" if independent else "implementer",
        implementer_id="implementer",
        context_fingerprint="a" * 64,
        implementation_context_fingerprint=("b" if independent else "a") * 64,
    )
    return IndependentReview(
        review_id=assurance_identifier("REVIEW", c.criterion_id, str(independent), str(blockers)),
        subject_id=c.work_item_id,
        identity=identity,
        criterion_ids=(c.criterion_id,),
        finding_count=blockers,
        blocking_finding_count=blockers,
        completed_at_utc=NOW,
    )


def test_fresh_verified_pass_is_passing_evidence():
    c = criterion()
    assessed = assess_evidence_for_criterion(c, (record(c, "EVID-1"),), now=NOW)
    assert assessed[0].state is CriterionState.PASS


def test_unverified_evidence_remains_unknown():
    c = criterion()
    assessed = assess_evidence_for_criterion(
        c, (record(c, "EVID-1", verified="UNVERIFIED"),), now=NOW
    )
    assert assessed[0].state is CriterionState.UNKNOWN


def test_failure_and_blocked_states_are_preserved():
    c = criterion()
    assessed = assess_evidence_for_criterion(
        c,
        (record(c, "EVID-1", result="FAIL"), record(c, "EVID-2", result="BLOCKED")),
        now=NOW,
    )
    assert [a.state for a in assessed] == [CriterionState.FAIL, CriterionState.BLOCKED]


def test_old_passing_evidence_becomes_stale():
    c = criterion()
    assessed = assess_evidence_for_criterion(c, (record(c, "EVID-1", age_days=31),), now=NOW)
    assert assessed[0].state is CriterionState.STALE


def test_high_risk_requires_multiple_methods_and_independent_review():
    c = criterion(AssuranceRisk.HIGH)
    one = assess_evidence_for_criterion(c, (record(c, "EVID-1", method="pytest unit"),), now=NOW)
    ok, reasons = evidence_sufficient(c, one, review=review(c))
    assert ok is False
    assert any("distinct" in r for r in reasons)


def test_high_risk_two_methods_plus_clean_review_is_sufficient():
    c = criterion(AssuranceRisk.HIGH)
    rows = (
        record(c, "EVID-1", method="pytest unit"),
        record(c, "EVID-2", method="integration contract"),
    )
    assessed = assess_evidence_for_criterion(c, rows, now=NOW)
    ok, reasons = evidence_sufficient(c, assessed, review=review(c))
    assert ok is True
    assert reasons == ()


def test_self_review_never_satisfies_high_risk_review():
    c = criterion(AssuranceRisk.HIGH)
    rows = (record(c, "EVID-1", method="pytest unit"), record(c, "EVID-2", method="integration"))
    assessed = assess_evidence_for_criterion(c, rows, now=NOW)
    ok, reasons = evidence_sufficient(c, assessed, review=review(c, independent=False))
    assert ok is False
    assert any("independent" in r for r in reasons)


def test_claim_and_verified_fact_remain_distinct_truth_types():
    claim = truth_from_claim("PP-TASK-X", "worker says complete", "worker")
    fact = verified_fact("PP-TASK-X", "tests prove behavior", ("EVID-1",), "verifier")
    assert claim.kind is TruthKind.CLAIM
    assert fact.kind is TruthKind.VERIFIED_FACT
    assert fact.evidence_ids == ("EVID-1",)


def test_verified_fact_records_verification_confidence_metadata():
    fact = verified_fact("subject", "verified behavior", ("EVID-1",), "reviewer")
    assert fact.verification_status == "VERIFIED"
    assert fact.confidence_milli == 1000
