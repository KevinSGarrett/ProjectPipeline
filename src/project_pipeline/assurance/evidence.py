from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.assurance.policy import AssurancePolicy
from project_pipeline.domain.assurance import (
    AcceptanceCriterion,
    AssuranceRisk,
    CriterionState,
    EvidenceAssessment,
    IndependentReview,
    TruthKind,
    TruthRecord,
    VerificationMethod,
    assurance_identifier,
)


def load_evidence(root: Path) -> tuple[dict, ...]:
    path = root / "evidence" / "EVIDENCE_LEDGER.jsonl"
    rows: list[dict] = []
    if not path.exists():
        return ()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return tuple(rows)


def infer_method(record: dict) -> VerificationMethod:
    text = " ".join(
        str(record.get(key, "")) for key in ("method", "claim", "artifact_path")
    ).lower()
    mapping = [
        ("property", VerificationMethod.PROPERTY),
        ("mutation", VerificationMethod.MUTATION),
        ("adversarial", VerificationMethod.ADVERSARIAL),
        ("fault", VerificationMethod.FAULT),
        ("performance", VerificationMethod.PERFORMANCE),
        ("security", VerificationMethod.SECURITY),
        ("accessibility", VerificationMethod.ACCESSIBILITY),
        ("visual", VerificationMethod.VISUAL),
        ("browser", VerificationMethod.BROWSER),
        ("golden", VerificationMethod.END_TO_END),
        ("end-to-end", VerificationMethod.END_TO_END),
        ("e2e", VerificationMethod.END_TO_END),
        ("integration", VerificationMethod.INTEGRATION),
        ("contract", VerificationMethod.CONTRACT),
        ("api", VerificationMethod.API),
        ("rollback", VerificationMethod.ROLLBACK),
        ("recovery", VerificationMethod.RECOVERY),
        ("documentation", VerificationMethod.DOCUMENTATION),
        ("review", VerificationMethod.REVIEW),
        ("pytest", VerificationMethod.UNIT),
        ("test", VerificationMethod.UNIT),
        ("traceability", VerificationMethod.TRACEABILITY),
        ("repository", VerificationMethod.STATIC),
    ]
    for token, method in mapping:
        if token in text:
            return method
    return VerificationMethod.STATIC


def assess_evidence_for_criterion(
    criterion: AcceptanceCriterion,
    records: tuple[dict, ...],
    *,
    now: datetime | None = None,
    policy: AssurancePolicy | None = None,
) -> tuple[EvidenceAssessment, ...]:
    policy = policy or AssurancePolicy()
    now = (now or datetime.now(UTC)).astimezone(UTC)
    assessments: list[EvidenceAssessment] = []
    for record in records:
        if criterion.criterion_id not in record.get("criterion_ids", ()):
            continue
        observed = datetime.fromisoformat(record["observed_at_utc"]).astimezone(UTC)
        age = max(0, int((now - observed).total_seconds()))
        if record.get("verification_status") != "VERIFIED":
            state = CriterionState.UNKNOWN
            reason = "evidence is not independently verified"
        elif record.get("result") == "FAIL":
            state = CriterionState.FAIL
            reason = "evidence records a failure"
        elif record.get("result") == "BLOCKED":
            state = CriterionState.BLOCKED
            reason = "evidence records an external or environmental block"
        elif record.get("result") != "PASS":
            state = CriterionState.UNKNOWN
            reason = "evidence does not record a passing result"
        elif age > policy.default_evidence_max_age_seconds:
            state = CriterionState.STALE
            reason = "passing evidence is older than the configured freshness ceiling"
        else:
            state = CriterionState.PASS
            reason = "verified passing evidence is fresh"
        assessments.append(
            EvidenceAssessment(
                evidence_id=record["evidence_id"],
                criterion_id=criterion.criterion_id,
                state=state,
                method=infer_method(record),
                producer_id=str(record.get("environment") or "unknown"),
                observed_at_utc=observed,
                age_seconds=age,
                max_age_seconds=policy.default_evidence_max_age_seconds,
                reason=reason,
            )
        )
    return tuple(sorted(assessments, key=lambda item: item.evidence_id))


def evidence_sufficient(
    criterion: AcceptanceCriterion,
    assessments: tuple[EvidenceAssessment, ...],
    *,
    review: IndependentReview | None = None,
    policy: AssurancePolicy | None = None,
) -> tuple[bool, tuple[str, ...]]:
    policy = policy or AssurancePolicy()
    passing = [item for item in assessments if item.state is CriterionState.PASS]
    reasons: list[str] = []
    if not passing:
        reasons.append("no fresh verified passing evidence covers the criterion")
    method_count = len({item.method for item in passing})
    required = 1
    if criterion.risk is AssuranceRisk.HIGH:
        required = policy.high_risk_min_distinct_methods
    elif criterion.risk is AssuranceRisk.CRITICAL:
        required = policy.critical_risk_min_distinct_methods
    if method_count < required:
        reasons.append(
            f"criterion requires {required} materially distinct evidence methods; observed {method_count}"
        )
    if (
        criterion.risk in {AssuranceRisk.HIGH, AssuranceRisk.CRITICAL}
        and policy.require_independent_review_for_high_risk
    ) and (review is None or not review.identity.independent or review.blocking_finding_count):
        reasons.append("high-risk criterion lacks a clean independent review")
    return not reasons, tuple(reasons)


def truth_from_claim(
    subject_id: str, statement: str, producer_id: str | None = None
) -> TruthRecord:
    return TruthRecord(
        truth_id=assurance_identifier("TRUTH", subject_id, TruthKind.CLAIM.value, statement),
        subject_id=subject_id,
        kind=TruthKind.CLAIM,
        statement=statement,
        producer_id=producer_id,
        verification_status="UNVERIFIED",
    )


def verified_fact(
    subject_id: str, statement: str, evidence_ids: tuple[str, ...], producer_id: str | None = None
) -> TruthRecord:
    return TruthRecord(
        truth_id=assurance_identifier(
            "TRUTH", subject_id, TruthKind.VERIFIED_FACT.value, statement, *evidence_ids
        ),
        subject_id=subject_id,
        kind=TruthKind.VERIFIED_FACT,
        statement=statement,
        evidence_ids=evidence_ids,
        producer_id=producer_id,
        verification_status="VERIFIED",
        confidence_milli=1000,
    )
