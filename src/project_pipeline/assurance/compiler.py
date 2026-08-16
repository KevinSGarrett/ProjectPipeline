from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.assurance.policy import AssurancePolicy
from project_pipeline.domain.assurance import (
    AcceptanceCriterion,
    AssuranceRisk,
    VerificationMethod,
    VerificationPlan,
    assurance_fingerprint,
    assurance_identifier,
)
from project_pipeline.jira import load_issues

_METHOD_MAP = {
    "automated_behavior_validation": VerificationMethod.COMPONENT,
    "repository_contract_validation": VerificationMethod.TRACEABILITY,
    "pytest": VerificationMethod.UNIT,
    "unit": VerificationMethod.UNIT,
    "component": VerificationMethod.COMPONENT,
    "contract": VerificationMethod.CONTRACT,
    "api": VerificationMethod.API,
    "integration": VerificationMethod.INTEGRATION,
    "e2e": VerificationMethod.END_TO_END,
    "end_to_end": VerificationMethod.END_TO_END,
    "property": VerificationMethod.PROPERTY,
    "mutation": VerificationMethod.MUTATION,
    "adversarial": VerificationMethod.ADVERSARIAL,
    "fault": VerificationMethod.FAULT,
    "performance": VerificationMethod.PERFORMANCE,
    "security": VerificationMethod.SECURITY,
    "accessibility": VerificationMethod.ACCESSIBILITY,
    "visual": VerificationMethod.VISUAL,
    "browser": VerificationMethod.BROWSER,
    "resilience": VerificationMethod.RESILIENCE,
    "recovery": VerificationMethod.RECOVERY,
    "installer": VerificationMethod.INSTALLER,
    "upgrade": VerificationMethod.UPGRADE,
    "rollback": VerificationMethod.ROLLBACK,
    "review": VerificationMethod.REVIEW,
    "documentation": VerificationMethod.DOCUMENTATION,
}


def _risk(value: str | None) -> AssuranceRisk:
    raw = (value or "MEDIUM").upper()
    return AssuranceRisk(raw if raw in AssuranceRisk._value2member_map_ else "MEDIUM")


def _verification_method(value: Any) -> VerificationMethod:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in _METHOD_MAP:
        return _METHOD_MAP[text]
    for token, method in _METHOD_MAP.items():
        if token in text:
            return method
    return VerificationMethod.STATIC


def criterion_fingerprint(work_item_id: str, statement: str, verification: dict[str, Any]) -> str:
    return assurance_fingerprint(
        {
            "work_item_id": work_item_id,
            "statement": statement.strip(),
            "verification": verification,
        }
    )


def compile_issue_criteria(issue: dict[str, Any]) -> tuple[AcceptanceCriterion, ...]:
    result: list[AcceptanceCriterion] = []
    for raw in issue.get("acceptance_criteria", ()):
        statement = str(raw.get("statement", "")).strip()
        if not statement:
            continue
        verification = dict(raw.get("verification") or {})
        method = _verification_method(verification.get("method") or verification.get("command"))
        fingerprint = criterion_fingerprint(issue["local_id"], statement, verification)
        result.append(
            AcceptanceCriterion(
                criterion_id=assurance_identifier(
                    "CRIT", issue["local_id"], statement, fingerprint
                ),
                work_item_id=issue["local_id"],
                statement=statement,
                requirement_ids=tuple(sorted(set(issue.get("requirement_ids", ())))),
                risk=_risk(issue.get("risk_classification")),
                verification_methods=(method,),
                verification_command=verification.get("command"),
                verification_path=verification.get("path"),
                fixture_paths=tuple(
                    sorted(
                        set(
                            ([str(verification["fixture"])] if verification.get("fixture") else [])
                            + [str(item) for item in verification.get("fixtures", ())]
                        )
                    )
                ),
                objective=bool(
                    verification.get("method")
                    or verification.get("command")
                    or verification.get("path")
                ),
                frozen_fingerprint=fingerprint,
            )
        )
    return tuple(result)


def compile_repository_plan(
    root: Path, project_id: str, policy: AssurancePolicy | None = None
) -> VerificationPlan:
    policy = policy or AssurancePolicy()
    criteria: list[AcceptanceCriterion] = []
    for issue in load_issues(root):
        criteria.extend(compile_issue_criteria(issue))
    criteria.sort(key=lambda item: (item.work_item_id, item.criterion_id))
    unverifiable = [item.criterion_id for item in criteria if not item.objective]
    if unverifiable:
        raise ValueError(
            f"acceptance criteria are not objectively verifiable: {', '.join(unverifiable)}"
        )
    required = {
        AssuranceRisk.HIGH.value: policy.high_risk_min_distinct_methods,
        AssuranceRisk.CRITICAL.value: policy.critical_risk_min_distinct_methods,
    }
    fingerprint = assurance_fingerprint([item.model_dump(mode="json") for item in criteria])
    return VerificationPlan(
        plan_id=assurance_identifier("VPLAN", project_id, fingerprint),
        project_id=project_id,
        criteria=tuple(criteria),
        required_method_counts=required,
        independent_review_required=any(
            item.risk in {AssuranceRisk.HIGH, AssuranceRisk.CRITICAL} for item in criteria
        ),
        max_verification_attempts=policy.verification_max_attempts,
        max_evidence_records=policy.verification_max_evidence_records,
        fingerprint=fingerprint,
    )
