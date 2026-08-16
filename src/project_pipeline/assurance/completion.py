from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.domain.assurance import (
    CandidateCompletionAssessment,
    CandidateCompletionState,
    CompletionFailure,
    CompletionGateDecision,
    CompletionGateFacts,
    CompletionQuestionResult,
    FailureCategory,
    GateState,
    assurance_fingerprint,
    assurance_identifier,
)
from project_pipeline.domain.requirements import ImplementationState, RequirementDisposition
from project_pipeline.jira import load_issues
from project_pipeline.requirements import load_requirement_catalog

_COMPLETE = {
    ImplementationState.IMPLEMENTED.value,
    ImplementationState.MOCK_VERIFIED.value,
    ImplementationState.LIVE_VERIFIED.value,
    ImplementationState.BLOCKED_EXTERNAL.value,
}

QUESTIONS: tuple[str, ...] = (
    "Are all source-derived requirements dispositioned?",
    "Are all accepted requirements implemented or explicitly externally blocked?",
    "Are all implementation artifacts traceable?",
    "Are all critical paths tested?",
    "Do the golden journeys pass?",
    "Are security gates satisfied?",
    "Are resilience/recovery expectations verified?",
    "Is deployment reproducible?",
    "Is rollback documented and tested where practical?",
    "Can another engineer operate the system from the supplied documentation?",
    "Can another AI continue development using the repository and Jira structure?",
    "Are unresolved items accurately represented rather than hidden?",
    "Does the Command Center accurately reflect actual system state?",
    "Does Jira accurately reflect actual implementation state?",
    "Does the final coverage audit show any unexplained gaps?",
)

_CATEGORY_BY_QUESTION = {
    1: FailureCategory.REQUIREMENT,
    2: FailureCategory.REQUIREMENT,
    3: FailureCategory.TRACEABILITY,
    4: FailureCategory.TEST,
    5: FailureCategory.GOLDEN_JOURNEY,
    6: FailureCategory.SECURITY,
    7: FailureCategory.RESILIENCE,
    8: FailureCategory.DEPLOYMENT,
    9: FailureCategory.ROLLBACK,
    10: FailureCategory.DOCUMENTATION,
    11: FailureCategory.CONTINUATION,
    12: FailureCategory.STATE_RECONCILIATION,
    13: FailureCategory.STATE_RECONCILIATION,
    14: FailureCategory.STATE_RECONCILIATION,
    15: FailureCategory.COVERAGE,
}


def assess_candidate_completion(
    *,
    work_item_id: str,
    implementer_id: str,
    criteria_total: int,
    criteria_passing: int,
    stale_evidence_count: int,
    unknown_count: int,
    independent_review_required: bool,
    independent_review_satisfied: bool,
) -> CandidateCompletionAssessment:
    reasons: list[str] = []
    if criteria_passing < criteria_total:
        reasons.append(f"{criteria_total - criteria_passing} acceptance criteria are not passing")
    if stale_evidence_count:
        reasons.append(f"{stale_evidence_count} evidence records are stale")
    if unknown_count:
        reasons.append(f"{unknown_count} acceptance facts remain unknown")
    if independent_review_required and not independent_review_satisfied:
        reasons.append("required independent review is not satisfied")
    if reasons:
        state = CandidateCompletionState.CHALLENGE
    else:
        state = CandidateCompletionState.READY_FOR_COMPLETION_GATE
        reasons.append(
            "candidate completion satisfies criterion/evidence/review prerequisites; final Completion Gate is still required"
        )
    return CandidateCompletionAssessment(
        assessment_id=assurance_identifier(
            "CAND",
            work_item_id,
            implementer_id,
            str(criteria_total),
            str(criteria_passing),
            str(stale_evidence_count),
            str(unknown_count),
            str(independent_review_satisfied),
        ),
        work_item_id=work_item_id,
        state=state,
        implementer_id=implementer_id,
        criteria_total=criteria_total,
        criteria_passing=criteria_passing,
        stale_evidence_count=stale_evidence_count,
        unknown_count=unknown_count,
        independent_review_required=independent_review_required,
        independent_review_satisfied=independent_review_satisfied,
        reasons=tuple(reasons),
    )


def evaluate_completion_gate(facts: CompletionGateFacts) -> CompletionGateDecision:
    values = (
        facts.source_requirements_dispositioned,
        facts.accepted_requirements_complete_or_external,
        facts.implementation_traceability_complete,
        facts.critical_paths_tested,
        facts.golden_journeys_pass,
        facts.security_gates_satisfied,
        facts.resilience_verified,
        facts.deployment_reproducible,
        facts.rollback_verified,
        facts.engineer_operable_from_docs,
        facts.ai_continuable_from_repo_and_jira,
        facts.unresolved_items_truthful,
        facts.command_center_truthful,
        facts.jira_truthful,
        facts.unexplained_gap_count == 0,
    )
    blocked = set(facts.externally_blocked_question_numbers)
    results: list[CompletionQuestionResult] = []
    failures: list[CompletionFailure] = []
    for number, (question, passed) in enumerate(zip(QUESTIONS, values, strict=True), start=1):
        reasons = facts.reasons_by_question.get(str(number), ())
        if not reasons:
            reasons = (
                ("satisfied by deterministic repository facts",)
                if passed
                else ("completion prerequisite is not satisfied",)
            )
        result = CompletionQuestionResult(
            question_number=number,
            question=question,
            passed=bool(passed),
            externally_blocked=(number in blocked and not passed),
            reasons=tuple(reasons),
            evidence_ids=facts.evidence_by_question.get(str(number), ()),
        )
        results.append(result)
        if not passed:
            failures.append(
                CompletionFailure(
                    failure_id=assurance_identifier(
                        "FAIL", facts.project_id, str(number), facts.snapshot_fingerprint
                    ),
                    category=_CATEGORY_BY_QUESTION[number],
                    subject_id=facts.project_id,
                    detail="; ".join(reasons),
                    rework_route=f"completion.question.{number}",
                )
            )
    final = all(values)
    if final:
        state = GateState.COMPLETE
    elif failures and all(item.question_number in blocked for item in results if not item.passed):
        state = GateState.BLOCKED_EXTERNAL
    else:
        state = GateState.NOT_COMPLETE
    return CompletionGateDecision(
        gate_id=assurance_identifier(
            "GATE", facts.project_id, facts.snapshot_fingerprint, state.value
        ),
        project_id=facts.project_id,
        state=state,
        questions=tuple(results),
        failures=tuple(failures),
        source_snapshot_fingerprint=facts.snapshot_fingerprint,
        final_complete=final,
    )


def build_repository_gate_facts(root: Path, project_id: str) -> CompletionGateFacts:
    requirements = load_requirement_catalog(root)
    accepted = [
        item
        for item in requirements
        if item.get("disposition") == RequirementDisposition.ACCEPTED.value
    ]
    issues = load_issues(root)
    traceability = json.loads(
        (root / "plans/_traceability/coverage_report.json").read_text(encoding="utf-8")
    )
    dispositioned = all(item.get("disposition") for item in requirements)
    req_complete = all(item.get("implementation_state") in _COMPLETE for item in accepted)
    traceable = all(
        item.get("implementation_state") not in _COMPLETE or bool(item.get("implementation_paths"))
        for item in accepted
    )
    critical = [
        item
        for item in accepted
        if item.get("priority") == "P0" and item.get("risk") in {"HIGH", "CRITICAL"}
    ]
    critical_tested = bool(critical) and all(
        item.get("test_ids") and item.get("evidence_ids") for item in critical
    )
    evidence_rows = _evidence_rows(root)
    golden_evidence = tuple(
        sorted(
            item["evidence_id"]
            for item in evidence_rows
            if "golden" in str(item.get("method", "")).lower()
            and item.get("result") == "PASS"
            and item.get("verification_status") == "VERIFIED"
        )
    )
    golden = bool(golden_evidence)
    sec = [item for item in accepted if item.get("domain") == "SEC"]
    security = bool(sec) and all(
        item.get("implementation_state") in _COMPLETE and item.get("evidence_ids") for item in sec
    )
    res = [item for item in accepted if item.get("domain") == "RES"]
    resilience = bool(res) and all(
        item.get("implementation_state") in _COMPLETE and item.get("evidence_ids") for item in res
    )
    infra = [item for item in accepted if item.get("domain") == "INFRA"]
    deployment = bool(infra) and all(
        item.get("implementation_state") in _COMPLETE and item.get("evidence_ids") for item in infra
    )
    migration_catalog = json.loads(
        (root / "database/MIGRATION_CATALOG.json").read_text(encoding="utf-8")
    )
    rollback = all(
        item.get("reversible") and item.get("sqlite_down_path") and item.get("postgresql_down_path")
        for item in migration_catalog.get("migrations", [])
    )
    engineer_docs = all((root / path).exists() for path in ("README.md", "docs", "runbooks"))
    ai_continue = all(
        (root / path).exists()
        for path in (
            "jira/indexes/issues.jsonl",
            "plans/_traceability/requirements.jsonl",
            "architecture/component_catalog.json",
        )
    )
    unresolved_truthful = all(
        not (item.get("state") == "DONE" and item.get("implementation_state") == "PLANNED_ONLY")
        for item in issues
    )
    ux = [item for item in accepted if item.get("domain") == "UX"]
    command_center = bool(ux) and all(item.get("implementation_state") in _COMPLETE for item in ux)
    jira_truthful = all(
        not (item.get("state") == "DONE" and not item.get("completion_evidence")) for item in issues
    )
    gaps = int(traceability.get("unexplained_gap_count", traceability.get("gap_count", 0)))
    reasons = {
        "1": (f"{len(requirements)} requirements inspected",),
        "2": (
            f"{sum(item.get('implementation_state') not in _COMPLETE for item in accepted)} accepted requirements remain incomplete",
        )
        if not req_complete
        else ("all accepted requirements are implemented or externally blocked",),
        "4": (
            f"{sum(not (item.get('test_ids') and item.get('evidence_ids')) for item in critical)} critical requirements lack test/evidence coverage",
        )
        if not critical_tested
        else ("critical requirement set has test/evidence mappings",),
        "5": (
            "golden-journey verified evidence is not yet present; execution belongs to the next verification harness phase",
        )
        if not golden
        else ("verified golden-journey evidence is present",),
        "13": ("Command Center requirements are not yet complete",)
        if not command_center
        else ("Command Center requirements are complete",),
        "15": (f"unexplained traceability gaps: {gaps}",),
    }
    payload = {
        "requirements": [
            (
                i["requirement_id"],
                i.get("implementation_state"),
                tuple(i.get("test_ids", ())),
                tuple(i.get("evidence_ids", ())),
            )
            for i in requirements
        ],
        "issues": [(i["local_id"], i.get("state"), i.get("implementation_state")) for i in issues],
        "gaps": gaps,
        "golden": golden,
        "rollback": rollback,
    }
    return CompletionGateFacts(
        project_id=project_id,
        source_requirements_dispositioned=dispositioned,
        accepted_requirements_complete_or_external=req_complete,
        implementation_traceability_complete=traceable,
        critical_paths_tested=critical_tested,
        golden_journeys_pass=golden,
        security_gates_satisfied=security,
        resilience_verified=resilience,
        deployment_reproducible=deployment,
        rollback_verified=rollback,
        engineer_operable_from_docs=engineer_docs,
        ai_continuable_from_repo_and_jira=ai_continue,
        unresolved_items_truthful=unresolved_truthful,
        command_center_truthful=command_center,
        jira_truthful=jira_truthful,
        unexplained_gap_count=gaps,
        evidence_by_question={
            "4": tuple(
                sorted(
                    {
                        evidence_id
                        for item in critical
                        for evidence_id in item.get("evidence_ids", [])
                    }
                )
            ),
            "5": golden_evidence,
            "6": tuple(
                sorted(
                    {evidence_id for item in sec for evidence_id in item.get("evidence_ids", [])}
                )
            ),
            "7": tuple(
                sorted(
                    {evidence_id for item in res for evidence_id in item.get("evidence_ids", [])}
                )
            ),
            "8": tuple(
                sorted(
                    {evidence_id for item in infra for evidence_id in item.get("evidence_ids", [])}
                )
            ),
        },
        reasons_by_question=reasons,
        snapshot_fingerprint=assurance_fingerprint(payload),
    )


def _evidence_rows(root: Path) -> tuple[dict, ...]:
    rows = []
    path = root / "evidence/EVIDENCE_LEDGER.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return tuple(rows)
