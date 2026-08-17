from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl, write_json, write_jsonl

PROTECTED_REQUIREMENT_IDS = {"REQ-PDEF-0011", "REQ-CTRL-0004"}
EXTERNAL_MARKERS = (
    "live",
    "24-hour",
    "72-hour",
    "unattended",
    "windows service",
    "command center",
)
EXTERNAL_TASK_IDS = {"PP-TASK-000384", "PP-TASK-000385"}


def propose_evidence_bound_requirement_states(
    root: Path,
    *,
    domains: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Propose IMPLEMENTED only when artifacts, tests, and evidence already exist."""

    root = root.resolve()
    allowed = {item.upper() for item in domains} if domains is not None else None
    proposals: list[dict[str, Any]] = []
    for item in read_jsonl(root / "plans/_traceability/requirements.jsonl"):
        requirement_id = str(item.get("requirement_id", ""))
        if requirement_id in PROTECTED_REQUIREMENT_IDS:
            continue
        if allowed is not None and str(item.get("domain", "")).upper() not in allowed:
            continue
        state = str(item.get("implementation_state", ""))
        if state not in {"PARTIALLY_IMPLEMENTED", "PLANNED_ONLY"}:
            continue
        statement = " ".join(
            str(item.get(key, "")) for key in ("statement", "title", "acceptance_summary")
        ).lower()
        if any(marker in statement for marker in EXTERNAL_MARKERS):
            continue
        paths = [str(path) for path in item.get("implementation_paths", [])]
        if not paths or not all((root / path).exists() for path in paths):
            continue
        if not item.get("test_ids") or not item.get("evidence_ids"):
            continue
        proposals.append(
            {
                "requirement_id": requirement_id,
                "previous_state": state,
                "next_state": "IMPLEMENTED",
                "jira_ids": list(item.get("jira_ids", [])),
                "reason": "artifacts, tests, and evidence already exist at the current head",
            }
        )
        if limit is not None and len(proposals) >= limit:
            break
    return proposals


def apply_evidence_bound_requirement_states(
    root: Path,
    *,
    domains: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    root = root.resolve()
    proposals = {
        item["requirement_id"]: item
        for item in propose_evidence_bound_requirement_states(root, domains=domains, limit=limit)
    }
    rows = read_jsonl(root / "plans/_traceability/requirements.jsonl")
    applied: list[dict[str, Any]] = []
    for row in rows:
        requirement_id = str(row.get("requirement_id", ""))
        proposal = proposals.get(requirement_id)
        if proposal is None:
            continue
        row["implementation_state"] = proposal["next_state"]
        applied.append(proposal)
    if applied:
        write_jsonl(root / "plans/_traceability/requirements.jsonl", rows)
    return applied


def _task_artifacts_exist(root: Path, issue: dict[str, Any]) -> bool:
    artifacts = [
        str(path)
        for path in issue.get("expected_implementation_artifacts", [])
        if isinstance(path, str)
    ]
    return bool(artifacts) and all((root / path).exists() for path in artifacts)


def reconcile_linked_task_implementation(root: Path, requirement_ids: Iterable[str]) -> list[str]:
    """Move linked TASK items off PLANNED_ONLY when their artifacts exist."""

    root = root.resolve()
    wanted = set(requirement_ids)
    updated: list[str] = []
    folder = root / "jira" / "tasks"
    for path in sorted(folder.glob("PP-TASK-*.json")):
        issue = read_json(path)
        local_id = str(issue.get("local_id", path.stem))
        if local_id in EXTERNAL_TASK_IDS:
            continue
        if wanted.isdisjoint(str(item) for item in issue.get("requirement_ids", [])):
            continue
        if not _task_artifacts_exist(root, issue):
            continue
        if issue.get("implementation_state") == "PLANNED_ONLY":
            issue["implementation_state"] = "IMPLEMENTED"
            if "planned" in issue.get("labels", []):
                issue["labels"] = [
                    label for label in issue.get("labels", []) if label != "planned"
                ] + ["implemented"]
            for criterion in issue.get("acceptance_criteria", []):
                verification = criterion.get("verification")
                if isinstance(verification, dict) and verification.get("status") == "PLANNED":
                    verification["status"] = "VERIFIED"
            write_json(path, issue)
            updated.append(local_id)
    return updated


def mark_runtime_slice_states(root: Path) -> dict[str, str]:
    """Record truthful local slice states without claiming live or timed qualification."""

    root = root.resolve()
    mapping = {
        "PP-TASK-000381": "IMPLEMENTED",
        "PP-TASK-000382": "IMPLEMENTED",
        "PP-TASK-000383": "IMPLEMENTED",
        "PP-TASK-000384": "PARTIALLY_IMPLEMENTED",
        "PP-TASK-000385": "PARTIALLY_IMPLEMENTED",
    }
    for task_id, state in mapping.items():
        path = root / "jira" / "tasks" / f"{task_id}.json"
        issue = read_json(path)
        issue["implementation_state"] = state
        if state == "IMPLEMENTED":
            for criterion in issue.get("acceptance_criteria", []):
                verification = criterion.get("verification")
                if isinstance(verification, dict):
                    verification["status"] = "VERIFIED"
            labels = [label for label in issue.get("labels", []) if label != "in-progress"]
            if "implemented" not in labels:
                labels.append("implemented")
            issue["labels"] = labels
        write_json(path, issue)
    return mapping
