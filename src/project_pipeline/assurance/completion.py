from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_pipeline.assurance.qualification_environments import compile_qualification_environments
from project_pipeline.autonomy_runtime.campaign import inspect_worktree_identity
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

_AUTONOMOUS_RUNTIME_EVIDENCE_ENVIRONMENTS = {
    "deterministic_unit_and_contract",
    "local_real_integrated_journey",
    "isolated_real_git_worktree_journey",
    "authorized_github_jira_sandbox_or_live",
    "qualified_real_worker_provider_dispatch",
    "windows_service_and_command_center",
    "recovery_and_restart",
    "unattended_24_hour",
    "unattended_72_hour",
    "released_post_release_completion_gate",
}

QUESTIONS: tuple[str, ...] = (
    "Are all source-derived requirements dispositioned?",
    "Are all accepted requirements implemented or explicitly externally blocked?",
    "Are all implementation artifacts traceable?",
    "Are all critical paths tested?",
    "Does the integrated autonomous operating-loop journey pass every qualification stage?",
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
    "Has the unattended end-to-end operating loop passed required qualification?",
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
    16: FailureCategory.GOLDEN_JOURNEY,
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
        facts.golden_journeys_pass and facts.autonomous_runtime_qualified,
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
        facts.unattended_operating_loop_qualified,
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


def build_repository_gate_facts(
    root: Path, project_id: str, *, external_live_qualification: Path | None = None
) -> CompletionGateFacts:
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
    identity = inspect_worktree_identity(root)
    compiler = compile_qualification_environments(
        root,
        identity=identity,
        live_qualification_path=external_live_qualification,
    )
    current_sha = str(identity.get("sha") or "").lower()
    current_tree = str(identity.get("tree") or "").lower()
    ancestor_blocked = bool(compiler.get("inherited_ancestor"))
    compiler_unbound = (
        not bool(identity.get("ok"))
        or bool(identity.get("dirty"))
        or compiler.get("bound_head") != current_sha
        or compiler.get("bound_tree") != current_tree
        or len(current_sha) != 40
        or len(current_tree) != 40
    )
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
    core_requirement = next(
        (item for item in requirements if item.get("requirement_id") == "REQ-PDEF-0011"),
        None,
    )
    core_evidence_ids = set(core_requirement.get("evidence_ids", [])) if core_requirement else set()
    runtime_evidence = tuple(
        item
        for item in evidence_rows
        if item.get("evidence_id") in core_evidence_ids
        and item.get("result") == "PASS"
        and item.get("verification_status") == "VERIFIED"
        and _evidence_matches_current_identity(root, item, current_sha, current_tree)
    )
    runtime_environments = {str(item.get("environment")) for item in runtime_evidence}
    missing_runtime_environments = sorted(
        _AUTONOMOUS_RUNTIME_EVIDENCE_ENVIRONMENTS - runtime_environments
    )
    autonomous_runtime_qualified = core_requirement is not None and (
        core_requirement.get("implementation_state") == ImplementationState.LIVE_VERIFIED.value
        and not missing_runtime_environments
        and compiler.get("ok") is True
        and not ancestor_blocked
        and not compiler_unbound
    )
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
    unattended_evidence = tuple(
        sorted(
            item["evidence_id"]
            for item in evidence_rows
            if item.get("method") == "unattended_operating_loop_qualification"
            and item.get("result") == "PASS"
            and item.get("verification_status") == "VERIFIED"
            and _valid_unattended_qualification(root, item)
        )
    )
    unattended_qualified = bool(unattended_evidence)
    reasons: dict[str, tuple[str, ...]] = {
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
            _question_five_reason(
                autonomous_runtime_qualified=autonomous_runtime_qualified,
                missing_runtime_environments=missing_runtime_environments,
                ancestor_blocked=ancestor_blocked,
                compiler_unbound=compiler_unbound,
            ),
        ),
        "13": ("Command Center requirements are not yet complete",)
        if not command_center
        else ("Command Center requirements are complete",),
        "15": (f"unexplained traceability gaps: {gaps}",),
        "16": (
            "no verified 72-hour unattended operating-loop qualification evidence is present"
            if not unattended_qualified
            else "verified 72-hour unattended operating-loop qualification evidence is present",
        ),
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
        "autonomous_runtime_qualified": autonomous_runtime_qualified,
        "autonomous_runtime_environments": sorted(runtime_environments),
        "rollback": rollback,
        "unattended_evidence": unattended_evidence,
    }
    return CompletionGateFacts(
        project_id=project_id,
        source_requirements_dispositioned=dispositioned,
        accepted_requirements_complete_or_external=req_complete,
        implementation_traceability_complete=traceable,
        critical_paths_tested=critical_tested,
        golden_journeys_pass=golden,
        autonomous_runtime_qualified=autonomous_runtime_qualified,
        security_gates_satisfied=security,
        resilience_verified=resilience,
        deployment_reproducible=deployment,
        rollback_verified=rollback,
        engineer_operable_from_docs=engineer_docs,
        ai_continuable_from_repo_and_jira=ai_continue,
        unresolved_items_truthful=unresolved_truthful,
        command_center_truthful=command_center,
        jira_truthful=jira_truthful,
        unattended_operating_loop_qualified=unattended_qualified,
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
            "5": tuple(
                sorted(
                    set(golden_evidence) | {str(item["evidence_id"]) for item in runtime_evidence}
                )
            ),
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
            "16": unattended_evidence,
        },
        reasons_by_question=reasons,
        snapshot_fingerprint=assurance_fingerprint(payload),
    )


def _question_five_reason(
    *,
    autonomous_runtime_qualified: bool,
    missing_runtime_environments: list[str],
    ancestor_blocked: bool,
    compiler_unbound: bool,
) -> str:
    if autonomous_runtime_qualified:
        return (
            "the integrated autonomous runtime has verified evidence for every "
            "required qualification stage"
        )
    parts: list[str] = []
    if ancestor_blocked:
        parts.append("ancestor_or_different_head_receipt")
    if compiler_unbound:
        parts.append("current_sha_tree_binding_missing")
    if missing_runtime_environments:
        parts.append("missing verified stages: " + ", ".join(missing_runtime_environments))
    if not parts:
        parts.append("integrated autonomous-runtime qualification is incomplete")
    return "integrated autonomous-runtime qualification is incomplete; " + "; ".join(parts)


def _evidence_matches_current_identity(
    root: Path, row: dict[str, Any], sha: str, tree: str
) -> bool:
    environment = str(row.get("environment") or "")
    if environment not in _AUTONOMOUS_RUNTIME_EVIDENCE_ENVIRONMENTS:
        return True
    artifact_path = row.get("artifact_path")
    if not isinstance(artifact_path, str):
        return False
    path = (root / artifact_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    bound_head = str(payload.get("bound_head") or "").strip().lower()
    bound_tree = str(payload.get("bound_tree") or "").strip().lower()
    return bound_head == sha and bound_tree == tree and len(sha) == 40 and len(tree) == 40


def _evidence_rows(root: Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    path = root / "evidence/EVIDENCE_LEDGER.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return tuple(rows)


def _valid_unattended_qualification(root: Path, row: dict[str, Any]) -> bool:
    artifact_path = row.get("artifact_path")
    if not isinstance(artifact_path, str):
        return False
    path = (root / artifact_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        float(payload.get("duration_hours", 0)) >= 72
        and payload.get("end_to_end") is True
        and payload.get("restart_recovery") is True
        and payload.get("external_reconciliation") is True
        and payload.get("windows_native_verified") is True
        and payload.get("unattended") is True
    )
