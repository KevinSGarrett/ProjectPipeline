from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl

CORE_REQUIREMENT_ID = "REQ-PDEF-0011"
CORE_EPIC_ID = "PP-EPIC-000036"
CORE_STATEMENT = (
    "ProjectPipeline shall continuously take a project from intake through verified modeling, "
    "autonomous selection, conflict-safe parallel execution, verification, governed repository "
    "integration, Jira reconciliation, project-state recomputation, and next-work selection "
    "without requiring a human to drive each development session."
)
CORE_SOURCES = {"SRC-014:L000001-L000087", "SRC-015:L000001-L000113"}
CORE_SLICE_TASKS = {f"PP-TASK-{value:06d}" for value in range(380, 386)}
PURSUING_MILESTONES = (
    "Repair product definition, source coverage, requirements, plans, Jira, Control selection, and Completion Gate semantics.",
    "Implement the missing integrated Autonomy Runtime.",
    "Prove one complete local-real autonomous project journey.",
    "Qualify live GitHub/Jira and worker/provider integrations where authorized.",
    "Qualify the Command Center and Windows runtime.",
    "Pass unattended 24-hour and then 72-hour operating-loop qualifications.",
    "Complete security, resilience, deployment, release, and post-release verification.",
    "Keep the pursuing goal INCOMPLETE until all terminal conditions pass.",
)
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_LIVE_STAGES = (
    "windows_service_foreground",
    "command_center_truth",
    "local_provider_dispatch",
    "github_jira_governance",
    "cursor_cli_provider_dispatch",
)
ORIGINAL_USER_INTENT_SECTION_IDS = {
    "SRC-002-SEC-001",
    "SRC-003-SEC-001",
    "SRC-004-SEC-001",
    "SRC-006-SEC-001",
    "SRC-007-SEC-001",
    "SRC-008-SEC-001",
    "SRC-013-SEC-001",
    "SRC-014-SEC-001",
    "SRC-015-SEC-001",
    "SRC-017-SEC-001",
}
_QUALIFICATION_LADDER = (
    "DETERMINISTIC_UNIT_AND_CONTRACT",
    "LOCAL_REAL_INTEGRATED_JOURNEY",
    "ISOLATED_REAL_GIT_WORKTREE_JOURNEY",
    "AUTHORIZED_GITHUB_JIRA_SANDBOX_OR_LIVE",
    "QUALIFIED_REAL_WORKER_PROVIDER_DISPATCH",
    "WINDOWS_SERVICE_AND_COMMAND_CENTER",
    "RECOVERY_AND_RESTART",
    "UNATTENDED_24_HOUR",
    "UNATTENDED_72_HOUR",
    "RELEASED_POST_RELEASE_COMPLETION_GATE",
)
_SOURCE = re.compile(r"^(SRC-[0-9]{3}):L([0-9]{6})-L([0-9]{6})$")


def _current_git_identity(root: Path) -> tuple[str | None, str | None]:
    try:
        head_probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        tree_probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    head = head_probe.stdout.strip().lower()
    tree = tree_probe.stdout.strip().lower()
    if head_probe.returncode != 0 or tree_probe.returncode != 0:
        return None, None
    if _FULL_SHA.fullmatch(head) is None or _FULL_SHA.fullmatch(tree) is None:
        return None, None
    return head, tree


def runtime_qualification_is_bound(root: Path) -> bool:
    """True when PP-384 live qualification matches this checkout SHA and tree."""

    path = root / "evidence/autonomy_runtime/live_qualification/live_qualification_latest.json"
    if not path.is_file():
        return False
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    stages = {
        str(item.get("stage_id")): str(item.get("outcome"))
        for item in body.get("stages") or []
        if isinstance(item, dict)
    }
    if any(stages.get(stage_id) != "PASSED" for stage_id in _REQUIRED_LIVE_STAGES):
        return False
    head = str(body.get("bound_head") or "").strip().lower()
    tree = str(body.get("bound_tree") or "").strip().lower()
    if _FULL_SHA.fullmatch(head) is None or _FULL_SHA.fullmatch(tree) is None:
        return False
    current_head, current_tree = _current_git_identity(root)
    if current_head is None or current_tree is None:
        return False
    if head != current_head or tree != current_tree:
        return False
    return _desktop_exact_main_is_bound(root, head=head, tree=tree)


def _desktop_exact_main_is_bound(root: Path, *, head: str, tree: str) -> bool:
    path = root / "evidence/command_center/exact_main_desktop_journey.json"
    if not path.is_file():
        return False
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        str(body.get("bound_head") or "").strip().lower() == head
        and str(body.get("bound_tree") or "").strip().lower() == tree
        and body.get("native_window_observed") is True
        and body.get("bootstrap_ok") is True
        and body.get("installer_executed") is True
        and int(body.get("stale_token_status") or 0) == 401
    )


def _issue_sources(root: Path) -> dict[str, dict[str, Any]]:
    issues: dict[str, dict[str, Any]] = {}
    for directory in ("epics", "stories", "tasks", "subtasks", "bugs"):
        path = root / "jira" / directory
        if not path.exists():
            continue
        for issue_path in sorted(path.glob("*.json")):
            issue = read_json(issue_path)
            local_id = str(issue.get("local_id", ""))
            if local_id:
                issues[local_id] = issue
    return issues


def _ranges_overlap(reference: str, source_id: str, start: int, end: int) -> bool:
    match = _SOURCE.fullmatch(reference)
    if match is None or match.group(1) != source_id:
        return False
    return int(match.group(2)) <= end and int(match.group(3)) >= start


def _coverage_fraction(reference: str, contract_reference: str) -> float:
    candidate = _SOURCE.fullmatch(reference)
    contract = _SOURCE.fullmatch(contract_reference)
    if candidate is None or contract is None or candidate.group(1) != contract.group(1):
        return 0.0
    contract_start, contract_end = int(contract.group(2)), int(contract.group(3))
    overlap_start = max(int(candidate.group(2)), contract_start)
    overlap_end = min(int(candidate.group(3)), contract_end)
    if overlap_end < overlap_start:
        return 0.0
    return (overlap_end - overlap_start + 1) / (contract_end - contract_start + 1)


def _reconciliation_findings(root: Path) -> set[str]:
    path = root / "plans/reconciliation/IMPLEMENTED_REQUIREMENT_JIRA_AUDIT.json"
    if not path.exists():
        return set()
    document = read_json(path)
    return {
        str(item.get("requirement_id"))
        for item in document.get("findings", [])
        if item.get("status") == "RECONCILIATION_REQUIRED"
    }


def validate_product_outcome(root: Path) -> list[str]:
    """Fail closed when the original autonomous product outcome is lost or overclaimed."""

    root = root.resolve()
    errors: list[str] = []
    contract_path = root / "config/product_outcome.json"
    if not contract_path.exists():
        return ["product outcome contract is missing: config/product_outcome.json"]
    contract = read_json(contract_path)
    if contract.get("core_requirement_id") != CORE_REQUIREMENT_ID:
        errors.append(f"product outcome contract must name {CORE_REQUIREMENT_ID}")
    if contract.get("core_statement") != CORE_STATEMENT:
        errors.append("product outcome contract statement drifted")
    if set(contract.get("source_references", [])) != CORE_SOURCES:
        errors.append("product outcome contract must bind the exact autonomous-loop sources")
    if contract.get("terminal_rule") != (
        "INCOMPLETE_UNTIL_ALL_QUALIFICATION_STAGES_AND_COMPLETION_GATE_PASS"
    ):
        errors.append("product outcome terminal rule must remain fail closed")
    if tuple(contract.get("immediate_pursuing_milestones", [])) != PURSUING_MILESTONES:
        errors.append("product outcome pursuing milestones drifted from operator direction")
    selection = contract.get("control_selection", {})
    if not isinstance(selection, dict):
        errors.append("product outcome Control selection contract must be an object")
    else:
        mode = selection.get("mode")
        if mode not in {
            "PAUSED_PENDING_INDEPENDENT_PRODUCT_MODEL_AUDIT",
            "PRODUCT_OUTCOME_CRITICAL_PATH_ONLY",
        }:
            errors.append("ordinary Control selection must remain product-outcome bounded")
        if set(selection.get("allowed_issue_ids", [])) != CORE_SLICE_TASKS:
            errors.append("Control selection must be bounded to the six cohesive runtime slices")
        if not str(selection.get("resume_rule", "")).strip():
            errors.append(
                "Control selection requires an explicit independently audited resume rule"
            )

    requirements_path = root / "plans/_traceability/requirements.jsonl"
    requirements = {str(item.get("requirement_id")): item for item in read_jsonl(requirements_path)}
    plan_catalog = read_json(root / "plans/PLAN_CATALOG.json")
    plan_ids = {str(item.get("plan_id")) for item in plan_catalog.get("plans", [])}
    if contract.get("plan_id") not in plan_ids:
        errors.append("product outcome contract references an unknown plan ID")
    core = requirements.get(CORE_REQUIREMENT_ID)
    if core is None:
        errors.append(f"accepted product outcome requirement is missing: {CORE_REQUIREMENT_ID}")
    else:
        if core.get("disposition") != "ACCEPTED":
            errors.append("core product outcome requirement must be ACCEPTED")
        if core.get("statement") != CORE_STATEMENT:
            errors.append("core product outcome requirement statement drifted")
        if not set(core.get("source_references", [])) >= CORE_SOURCES:
            errors.append("core product outcome requirement lacks exact source coverage")
        if contract.get("plan_id") not in core.get("plan_ids", []):
            errors.append("core product outcome requirement is not linked to its runtime plan")
        if contract.get("epic_id") not in core.get("jira_ids", []):
            errors.append("core product outcome requirement is not linked to its runtime epic")

    intake = requirements.get("REQ-PDEF-0006")
    if intake is not None and any(
        _ranges_overlap(reference, "SRC-014", 1, 87)
        for reference in intake.get("source_references", [])
    ):
        errors.append(
            "narrow intake requirement REQ-PDEF-0006 may not claim the autonomous-loop source range"
        )
    director = requirements.get("REQ-CTRL-0004")
    if director is None:
        errors.append(
            "persistent Autonomy Director must remain incomplete until runtime qualification"
        )
    else:
        director_state = director.get("implementation_state")
        epic_linked = contract.get("epic_id") in director.get("jira_ids", [])
        if director_state == "IMPLEMENTED":
            if not runtime_qualification_is_bound(root):
                errors.append(
                    "persistent Autonomy Director must remain incomplete until runtime qualification"
                )
            if not epic_linked:
                errors.append(
                    "persistent Autonomy Director must link to the autonomous-runtime epic"
                )
        elif director_state == "PARTIALLY_IMPLEMENTED":
            if not epic_linked:
                errors.append(
                    "persistent Autonomy Director must link to the autonomous-runtime epic"
                )
        else:
            errors.append(
                "persistent Autonomy Director must remain incomplete until runtime qualification"
            )
    for source_contract in contract.get("broad_source_contracts", []):
        if not isinstance(source_contract, dict):
            errors.append("broad source contract entries must be objects")
            continue
        reference = str(source_contract.get("source_reference", ""))
        allowed = {
            str(source_contract.get("mandatory_requirement_id", "")),
            *(str(item) for item in source_contract.get("allowed_supporting_requirement_ids", [])),
        }
        if any(item and item not in requirements for item in allowed):
            errors.append(
                f"broad source range {reference} references unknown requirement IDs in contract"
            )
        for requirement_id, requirement in requirements.items():
            if requirement_id in allowed:
                continue
            if any(
                _coverage_fraction(candidate, reference) >= 0.75
                for candidate in requirement.get("source_references", [])
            ):
                errors.append(
                    f"broad source range {reference} is claimed by unrelated narrow requirement: "
                    f"{requirement_id}"
                )

    sections = {
        str(item.get("section_id")): item
        for item in read_jsonl(root / "plans/_traceability/source_sections.jsonl")
    }
    intent_contracts = contract.get("user_intent_contracts", {})
    if not isinstance(intent_contracts, dict):
        errors.append("product outcome user-intent contract map must be an object")
        intent_contracts = {}
    residual_user_context_ids = {
        section_id
        for section_id, section in sections.items()
        if section.get("disposition") == "USER_INTENT_CONTEXT"
    }
    if set(intent_contracts) != ORIGINAL_USER_INTENT_SECTION_IDS:
        errors.append("all ten original USER_INTENT_CONTEXT sections require explicit contracts")
    if residual_user_context_ids:
        errors.append(
            "mandatory operator outcomes may not remain silently classified as USER_INTENT_CONTEXT: "
            + ", ".join(sorted(residual_user_context_ids))
        )
    for section_id, required_ids in intent_contracts.items():
        section = sections.get(section_id)
        if section is None:
            errors.append(f"user-intent source section is missing: {section_id}")
            continue
        expected = set(required_ids) if isinstance(required_ids, list) else set()
        missing_requirements = sorted(item for item in expected if item not in requirements)
        if missing_requirements:
            errors.append(
                f"user-intent contract references unknown requirements for {section_id}: "
                + ", ".join(missing_requirements)
            )
        linked = set(section.get("requirement_ids", []))
        if not expected or not expected <= linked:
            errors.append(
                f"user-intent outcome mapping is not enforced by source coverage: {section_id}"
            )

    issues = _issue_sources(root)
    epic = issues.get(CORE_EPIC_ID)
    if (
        epic is None
        or epic.get("title") != "Autonomous Runtime Integration and Unattended Qualification"
    ):
        errors.append("cohesive autonomous-runtime implementation epic is missing")
    slices = contract.get("vertical_slices", [])
    if not isinstance(slices, list) or not 4 <= len(slices) <= 8:
        errors.append(
            "autonomous runtime must use a small bounded set of meaningful vertical slices"
        )
        slices = []
    for item in slices:
        if not isinstance(item, dict):
            errors.append("autonomous-runtime slice entry must be an object")
            continue
        story_id = str(item.get("story_id", ""))
        task_id = str(item.get("task_id", ""))
        if story_id not in issues or task_id not in issues:
            errors.append(
                f"autonomous-runtime slice is missing Jira source items: {story_id}/{task_id}"
            )
        elif issues[task_id].get("parent") != story_id:
            errors.append(f"autonomous-runtime task is not owned by its slice story: {task_id}")
    issue_ids = set(issues)
    for issue_id in selection.get("allowed_issue_ids", []):
        if issue_id not in issue_ids:
            errors.append(f"Control selection references unknown issue: {issue_id}")
            continue
        if issues[issue_id].get("issue_type") != "TASK":
            errors.append(f"Control selection may only include TASK work items: {issue_id}")
    journey_id = str(contract.get("qualification_journey_task_id", ""))
    journey = issues.get(journey_id)
    if journey is None or "local-real" not in str(journey.get("description", "")).casefold():
        errors.append("a cohesive local-real autonomous qualification journey is required")
    qualification_ladder = tuple(str(item) for item in contract.get("qualification_ladder", []))
    if qualification_ladder != _QUALIFICATION_LADDER:
        errors.append("qualification ladder must match the canonical ten-stage runtime contract")

    broad_audit_path = root / "plans/reconciliation/BROAD_SOURCE_RANGE_AUDIT.json"
    decisions_path = root / "plans/reconciliation/BROAD_SOURCE_RANGE_DECISIONS.json"
    if not broad_audit_path.exists() or not decisions_path.exists():
        errors.append("independent broad source-range audit and decisions are required")
    else:
        broad_audit = read_json(broad_audit_path)
        decisions = read_json(decisions_path)
        if (
            broad_audit.get("status") != "REVIEWED"
            or broad_audit.get("pending_independent_review_count") != 0
        ):
            errors.append("broad source-range audit must have zero pending semantic reviews")
        if broad_audit.get("independent_review_id") != decisions.get("review_id"):
            errors.append("broad source-range audit is not bound to its independent decisions")
        for finding in broad_audit.get("findings", []):
            if finding.get("status") == "PENDING_INDEPENDENT_SEMANTIC_REVIEW":
                errors.append(
                    "unreviewed broad source citation remains: "
                    f"{finding.get('requirement_id')} {finding.get('source_reference')}"
                )

    findings = _reconciliation_findings(root)
    for requirement_id, requirement in requirements.items():
        if requirement.get("implementation_state") != "IMPLEMENTED":
            continue
        linked_issues = [issues[item] for item in requirement.get("jira_ids", []) if item in issues]
        if (
            linked_issues
            and all(item.get("implementation_state") == "PLANNED_ONLY" for item in linked_issues)
            and requirement_id not in findings
        ):
            errors.append(
                "implemented requirement has only PLANNED_ONLY Jira items without an explicit "
                f"reconciliation finding: {requirement_id}"
            )

    if core is not None and core.get("implementation_state") in {"IMPLEMENTED", "LIVE_VERIFIED"}:
        evidence = {
            str(item.get("evidence_id")): item
            for item in read_jsonl(root / "evidence/EVIDENCE_LEDGER.jsonl")
        }
        linked_evidence = [
            evidence[item] for item in core.get("evidence_ids", []) if item in evidence
        ]
        observed_environments = {str(item.get("environment")) for item in linked_evidence}
        if not any(value.startswith("unattended_72_hour") for value in observed_environments):
            errors.append("core product outcome cannot be implemented without 72-hour evidence")
        if not any(value.startswith("released_post_release") for value in observed_environments):
            errors.append(
                "core product outcome cannot be implemented without released-state evidence"
            )
        if observed_environments and observed_environments <= {
            "local_build_environment",
            "windows_local_project_worktree",
        }:
            errors.append(
                "local, mocked, or deterministic evidence cannot qualify the product outcome"
            )
    return errors


def render_product_outcome_errors(root: Path) -> str:
    return json.dumps(validate_product_outcome(root), indent=2, ensure_ascii=False)
