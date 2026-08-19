"""Evidence-bound local Jira implementation and lifecycle reconciliation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from project_pipeline.assurance.evidence import load_evidence
from project_pipeline.assurance.requirement_reconciliation import (
    EXTERNAL_MARKERS,
    EXTERNAL_TASK_IDS,
    PROTECTED_REQUIREMENT_IDS,
    path_fingerprint,
    test_catalog,
)
from project_pipeline.io import read_json, read_jsonl, write_json
from project_pipeline.jira import load_issues, rebuild_jira_indexes

_COMPLETE_REQUIREMENT_STATES = {
    "IMPLEMENTED",
    "MOCK_VERIFIED",
    "LIVE_VERIFIED",
    "BLOCKED_EXTERNAL",
}
_DONE_ISSUE_TYPES = {"TASK", "SUBTASK", "STORY"}
_DIRECTORY = {
    "EPIC": "epics",
    "STORY": "stories",
    "TASK": "tasks",
    "SUBTASK": "subtasks",
    "BUG": "bugs",
    "SPIKE": "spikes",
}
_LIFECYCLE_PROTECTED = {"PP-TASK-000385"}
_LEAVE_REMOTE_DONE = {"PP-TASK-000384"}


def _content_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _issue_path(root: Path, issue: dict[str, Any]) -> Path:
    directory = _DIRECTORY.get(str(issue.get("issue_type")), "unknown")
    return root / "jira" / directory / f"{issue['local_id']}.json"


def _text_blob(issue: dict[str, Any]) -> str:
    parts = [
        str(issue.get("title", "")),
        str(issue.get("description", "")),
        str(issue.get("objective", "")),
    ]
    for criterion in issue.get("acceptance_criteria", []) or []:
        if isinstance(criterion, dict):
            parts.append(str(criterion.get("statement", "")))
    return " ".join(parts).casefold()


def evaluate_jira_implementation_reconciliation(root: Path) -> list[dict[str, Any]]:
    """Return one disposition row per local Jira issue."""

    root = root.resolve()
    requirements = {
        str(item["requirement_id"]): item
        for item in read_jsonl(root / "plans/_traceability/requirements.jsonl")
    }
    catalog = test_catalog(root)
    evidence = {str(row.get("evidence_id")): row for row in load_evidence(root)}
    issues = load_issues(root)
    children: dict[str, list[str]] = {}
    for issue in issues:
        parent = issue.get("parent")
        if parent:
            children.setdefault(str(parent), []).append(str(issue["local_id"]))
    by_id = {str(item["local_id"]): item for item in issues}
    rows: list[dict[str, Any]] = []
    for issue in issues:
        rows.append(
            _evaluate_issue(
                root,
                issue,
                requirements=requirements,
                catalog=catalog,
                evidence=evidence,
                children=children,
                by_id=by_id,
            )
        )
    return rows


def apply_jira_implementation_reconciliation(root: Path) -> dict[str, Any]:
    root = root.resolve()
    applied: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for _pass in range(3):
        ledger = evaluate_jira_implementation_reconciliation(root)
        pass_applied = 0
        for row in ledger:
            if not row.get("accepted"):
                continue
            path = root / str(row["path"])
            issue = read_json(path)
            if _content_hash(issue) != row["before_hash"]:
                continue
            if row.get("next_implementation_state"):
                issue["implementation_state"] = row["next_implementation_state"]
            if row.get("completion_evidence"):
                issue["completion_evidence"] = list(row["completion_evidence"])
            if row.get("next_lifecycle_state"):
                issue["state"] = row["next_lifecycle_state"]
            labels = {str(item) for item in issue.get("labels", [])}
            if row.get("next_implementation_state") == "IMPLEMENTED":
                labels.discard("planned")
                labels.add("implemented")
            if row.get("next_lifecycle_state") == "IN_PROGRESS":
                labels.add("in-progress")
            if row.get("next_lifecycle_state") == "DONE":
                labels.discard("in-progress")
                labels.add("done")
            issue["labels"] = sorted(labels)
            for criterion in issue.get("acceptance_criteria", []):
                verification = criterion.get("verification")
                if isinstance(verification, dict) and row.get("verify_acceptance"):
                    verification["status"] = "VERIFIED"
            write_json(path, issue)
            applied.append({**row, "after_hash": _content_hash(issue)})
            pass_applied += 1
        if pass_applied == 0:
            break
    indexes = rebuild_jira_indexes(root)
    return {
        "schema_version": "1.0.0",
        "applied_count": len(applied),
        "applied": applied,
        "ledger_count": len(ledger),
        "ledger": ledger,
        "indexes": indexes,
    }


def _evaluate_issue(
    root: Path,
    issue: dict[str, Any],
    *,
    requirements: dict[str, dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    issue_id = str(issue.get("local_id", ""))
    path = _issue_path(root, issue)
    relative = path.relative_to(root).as_posix()
    base = {
        "issue_id": issue_id,
        "issue_type": issue.get("issue_type"),
        "path": relative,
        "previous_lifecycle_state": issue.get("state"),
        "previous_implementation_state": issue.get("implementation_state"),
        "next_lifecycle_state": None,
        "next_implementation_state": None,
        "completion_evidence": list(issue.get("completion_evidence") or []),
        "verify_acceptance": False,
        "accepted": False,
        "reason": "",
        "before_hash": _content_hash(issue),
    }
    if issue.get("state") == "DONE":
        return {**base, "reason": "already DONE; never reopen"}
    if issue_id in _LEAVE_REMOTE_DONE:
        return {**base, "reason": "leave remote-Done item unchanged"}
    if issue_id in EXTERNAL_TASK_IDS or issue_id in _LIFECYCLE_PROTECTED:
        if issue_id == "PP-TASK-000385":
            return {
                **base,
                "reason": "PP-TASK-000385 stays locally BACKLOG until live Jira In Progress after merge",
            }
        return {**base, "reason": "timed or live qualification item is not presence-reconcilable"}
    linked = [
        requirements[item] for item in issue.get("requirement_ids", []) if item in requirements
    ]
    if not linked:
        return {**base, "reason": "no linked requirements"}
    complete_linked = all(
        item.get("implementation_state") in _COMPLETE_REQUIREMENT_STATES for item in linked
    )
    any_complete = any(
        item.get("implementation_state") in _COMPLETE_REQUIREMENT_STATES for item in linked
    )
    artifacts = [str(item) for item in issue.get("expected_implementation_artifacts", [])]
    artifacts_ok = bool(artifacts) and all(
        path_fingerprint(root, relative_path) for relative_path in artifacts
    )
    current_impl = str(issue.get("implementation_state") or "")
    projected_impl = None
    if current_impl == "PLANNED_ONLY" and any_complete:
        projected_impl = (
            "IMPLEMENTED" if complete_linked and artifacts_ok else "PARTIALLY_IMPLEMENTED"
        )
    elif current_impl == "PARTIALLY_IMPLEMENTED" and complete_linked and artifacts_ok:
        projected_impl = "IMPLEMENTED"
    live_wording = any(marker in _text_blob(issue) for marker in EXTERNAL_MARKERS)
    protected = any(item.get("requirement_id") in PROTECTED_REQUIREMENT_IDS for item in linked)
    if not complete_linked or live_wording or protected:
        if projected_impl and projected_impl != current_impl:
            return {
                **base,
                "accepted": True,
                "next_implementation_state": projected_impl,
                "reason": (
                    "implementation projection from completed linked requirements; "
                    "lifecycle stays short of DONE"
                ),
            }
        if not complete_linked:
            return {**base, "reason": "not every linked requirement is complete"}
        if protected:
            return {**base, "reason": "linked protected high-risk requirement"}
        return {
            **base,
            "reason": "live, timed, or Completion Gate wording blocks presence-only DoD",
        }
    if not artifacts:
        return {**base, "reason": "expected implementation artifacts are missing"}
    if not artifacts_ok:
        return {**base, "reason": "artifact missing, empty, or unfingerprintable"}
    required_tests = [str(item) for item in issue.get("required_tests", [])]
    if not required_tests:
        return {**base, "reason": "required tests are missing"}
    for test_id in required_tests:
        entry = catalog.get(test_id)
        if entry is None:
            return {**base, "reason": f"required test is not in TEST_CATALOG: {test_id}"}
        test_path = str(entry.get("path") or "")
        if not test_path or not (root / test_path).is_file():
            return {**base, "reason": f"cataloged test path is missing: {test_id}"}
    criteria = issue.get("acceptance_criteria") or []
    if not criteria:
        return {**base, "reason": "acceptance criteria are missing"}
    for criterion in criteria:
        if not isinstance(criterion, dict) or not isinstance(criterion.get("verification"), dict):
            return {**base, "reason": "acceptance verification is incomplete"}
        verification_path = criterion["verification"].get("path")
        if not isinstance(verification_path, str) or not (root / verification_path).exists():
            return {**base, "reason": "acceptance verification path is missing"}
    evidence_ids = sorted(
        {
            str(item)
            for requirement in linked
            for item in requirement.get("evidence_ids", [])
            if item
        }
        | {str(item) for item in issue.get("completion_evidence", []) if item}
    )
    if not evidence_ids:
        return {**base, "reason": "no verified evidence references"}
    for evidence_id in evidence_ids:
        record = evidence.get(evidence_id)
        if record is None:
            return {**base, "reason": f"evidence id is missing from the ledger: {evidence_id}"}
        if str(record.get("verification_status")) != "VERIFIED":
            return {**base, "reason": f"evidence {evidence_id} is not independently verified"}
        if str(record.get("result")) != "PASS":
            return {**base, "reason": f"evidence {evidence_id} does not record PASS"}
    if issue.get("blockers"):
        return {**base, "reason": "recorded blockers remain"}
    if not issue.get("definition_of_done"):
        return {**base, "reason": "Definition of Done is empty"}
    if str(issue.get("issue_type")) == "STORY":
        child_ids = children.get(issue_id, [])
        if child_ids and not all(by_id[child].get("state") == "DONE" for child in child_ids):
            next_impl = projected_impl or (None if current_impl == "IMPLEMENTED" else "IMPLEMENTED")
            if next_impl is None:
                return {**base, "reason": "story children are not all DONE"}
            return {
                **base,
                "accepted": True,
                "next_implementation_state": next_impl,
                "completion_evidence": evidence_ids,
                "verify_acceptance": True,
                "reason": "implementation projection only; story children are not all DONE",
            }
    if str(issue.get("issue_type")) not in _DONE_ISSUE_TYPES:
        next_impl = projected_impl or (None if current_impl == "IMPLEMENTED" else "IMPLEMENTED")
        if next_impl is None:
            return {**base, "reason": "structural issue already projected implemented"}
        return {
            **base,
            "accepted": True,
            "next_implementation_state": next_impl,
            "completion_evidence": evidence_ids,
            "verify_acceptance": True,
            "reason": "implementation projection only; lifecycle stays on structural types",
        }
    next_impl = projected_impl or (None if current_impl == "IMPLEMENTED" else "IMPLEMENTED")
    next_life = None if issue.get("state") == "DONE" else "DONE"
    if next_impl is None and next_life is None:
        return {**base, "reason": "already projected implemented and DONE"}
    return {
        **base,
        "accepted": True,
        "next_implementation_state": next_impl,
        "next_lifecycle_state": next_life,
        "completion_evidence": evidence_ids,
        "verify_acceptance": True,
        "reason": "linked requirements, cataloged tests, artifacts, and verified evidence satisfy DoD",
    }
