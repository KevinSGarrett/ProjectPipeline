from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl
from project_pipeline.validation.product_outcome import (
    CORE_EPIC_ID,
    CORE_REQUIREMENT_ID,
    ORIGINAL_USER_INTENT_SECTION_IDS,
)

_BOUNDED_SLICES = (
    "PP-TASK-000380",
    "PP-TASK-000381",
    "PP-TASK-000382",
    "PP-TASK-000383",
    "PP-TASK-000384",
    "PP-TASK-000385",
)
_EXTERNAL_GAPS = (
    "24-hour",
    "72-hour",
    "unattended",
    "live github",
    "live jira",
    "qualified provider",
    "windows service",
    "command center",
)


def _issue_map(root: Path) -> dict[str, dict[str, Any]]:
    issues: dict[str, dict[str, Any]] = {}
    for directory in ("epics", "stories", "tasks"):
        folder = root / "jira" / directory
        if not folder.exists():
            continue
        for path in folder.glob("PP-*.json"):
            issue = read_json(path)
            local_id = str(issue.get("local_id", path.stem))
            issues[local_id] = issue
    return issues


def _artifact_paths(issue: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("expected_implementation_artifacts", "expected_file_locations"):
        for item in issue.get(key, []) or []:
            if isinstance(item, str) and item not in values:
                values.append(item)
    return values


def _text_blob(issue: dict[str, Any]) -> str:
    parts = [
        str(issue.get("title", "")),
        str(issue.get("description", "")),
        str(issue.get("objective", "")),
        " ".join(str(item) for item in issue.get("definition_of_done", []) or []),
        " ".join(str(item) for item in issue.get("scope", []) or []),
    ]
    return " ".join(parts).casefold()


def audit_product_model(root: Path) -> dict[str, Any]:
    """Independent product-model audit. Does not call validate_product_outcome()."""

    root = root.resolve()
    errors: list[str] = []
    findings: list[dict[str, str]] = []
    contract_path = root / "config/product_outcome.json"
    if not contract_path.exists():
        return {
            "auditor": "product_model_audit",
            "independent_of": "validate_product_outcome",
            "errors": ["independent audit: product outcome contract is missing"],
            "findings": [],
            "genuinely_missing": [],
            "resume_authorized": False,
        }
    contract = read_json(contract_path)
    sections = {
        str(item.get("section_id")): item
        for item in read_jsonl(root / "plans/_traceability/source_sections.jsonl")
    }
    requirements = {
        str(item.get("requirement_id")): item
        for item in read_jsonl(root / "plans/_traceability/requirements.jsonl")
    }
    intents = contract.get("user_intent_contracts") or {}
    if not isinstance(intents, dict) or set(intents) != ORIGINAL_USER_INTENT_SECTION_IDS:
        errors.append("independent audit: ten explicit user-intent mappings drifted")
    for section_id, requirement_ids in intents.items() if isinstance(intents, dict) else []:
        section = sections.get(section_id)
        if section is None:
            errors.append(f"independent audit: missing user-intent section {section_id}")
            continue
        expected = [str(item) for item in requirement_ids or []]
        missing = [item for item in expected if item not in requirements]
        if missing:
            errors.append(f"independent audit: unknown intent requirements for {section_id}")
        linked = {str(item) for item in section.get("requirement_ids", [])}
        if expected and not set(expected) <= linked:
            errors.append(f"independent audit: intent mapping is not covered for {section_id}")
        if section.get("disposition") == "USER_INTENT_CONTEXT" and not expected:
            errors.append(f"independent audit: {section_id} silently dropped an operator outcome")
    plan_id = str(contract.get("plan_id", ""))
    catalog = read_json(root / "plans/PLAN_CATALOG.json")
    plan = next((item for item in catalog.get("plans", []) if item.get("plan_id") == plan_id), None)
    if plan is None:
        errors.append("independent audit: product-outcome plan is absent from the catalog")
    elif plan_id and not (root / str(plan.get("path", ""))).exists():
        errors.append("independent audit: product-outcome plan file is missing")
    issues = _issue_map(root)
    epic = issues.get(str(contract.get("epic_id") or CORE_EPIC_ID))
    if epic is None:
        errors.append("independent audit: cohesive autonomous-runtime epic is missing")
    journey_id = str(contract.get("qualification_journey_task_id", "PP-TASK-000383"))
    journey = issues.get(journey_id)
    if journey is None or "local-real" not in str(journey.get("description", "")).casefold():
        errors.append("independent audit: cohesive local-real journey is missing")
    genuinely_missing: list[str] = []
    for issue_id in _BOUNDED_SLICES:
        issue = issues.get(issue_id)
        if issue is None:
            errors.append(f"independent audit: bounded slice {issue_id} is missing")
            continue
        artifacts = _artifact_paths(issue)
        existing = [path for path in artifacts if (root / path).exists()]
        state = str(issue.get("implementation_state", ""))
        blob = _text_blob(issue)
        external = any(marker in blob for marker in _EXTERNAL_GAPS)
        if (
            state in {"IMPLEMENTED", "LIVE_VERIFIED", "MOCK_VERIFIED"}
            and artifacts
            and not existing
        ):
            errors.append(f"independent audit: {issue_id} is labeled implemented without artifacts")
        if state == "PLANNED_ONLY" and existing:
            findings.append(
                {
                    "issue_id": issue_id,
                    "kind": "STALE_PLANNED_LABEL",
                    "detail": "artifacts exist while Jira still projects PLANNED_ONLY",
                }
            )
        if state in {"IMPLEMENTED", "LIVE_VERIFIED"} and issue_id == "PP-TASK-000385":
            errors.append(
                "independent audit: PP-TASK-000385 cannot be complete without attested 24/72-hour evidence"
            )
        missing_critical = (not existing) or (
            state not in {"IMPLEMENTED", "LIVE_VERIFIED"}
            and (external or issue_id == "PP-TASK-000385")
        )
        if state in {"PLANNED_ONLY", "PARTIALLY_IMPLEMENTED", "BLOCKED_EXTERNAL"} and (
            not existing or external or issue_id in {"PP-TASK-000384", "PP-TASK-000385"}
        ):
            missing_critical = True
        if missing_critical:
            genuinely_missing.append(issue_id)
    core = requirements.get(CORE_REQUIREMENT_ID)
    if core is None:
        errors.append("independent audit: core product outcome requirement is missing")
    elif core.get("implementation_state") in {"IMPLEMENTED", "LIVE_VERIFIED"}:
        errors.append(
            "independent audit: core outcome cannot be implemented without 72-hour and release evidence"
        )
    if not genuinely_missing:
        errors.append(
            "independent audit: Control's top bounded work is not genuinely missing; labels are stale"
        )
    resume_authorized = not errors and bool(genuinely_missing)
    return {
        "auditor": "product_model_audit",
        "independent_of": "validate_product_outcome",
        "errors": errors,
        "findings": findings,
        "genuinely_missing": genuinely_missing,
        "resume_authorized": resume_authorized,
        "core_still_incomplete": core is None
        or core.get("implementation_state") not in {"IMPLEMENTED", "LIVE_VERIFIED"},
    }


def validate_independent_product_model_audit(root: Path) -> list[str]:
    return list(audit_product_model(root)["errors"])
