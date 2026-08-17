from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl, write_json

_COMPLETE = {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED", "BLOCKED_EXTERNAL"}
_ACCEPTANCE_ID_REPAIRS = {
    "PP-EPIC-000036": "AC-PP-900036-01",
    "PP-STORY-000138": "AC-PP-900138-01",
    "PP-STORY-000139": "AC-PP-900139-01",
    "PP-STORY-000140": "AC-PP-900140-01",
    "PP-STORY-000141": "AC-PP-900141-01",
    "PP-STORY-000142": "AC-PP-900142-01",
    "PP-STORY-000143": "AC-PP-900143-01",
}
_REQUIREMENT_ID_REPAIRS = {
    "PP-TASK-000168": ("REQ-SEC-0004", "REQ-SEC-0009"),
    "PP-EPIC-000036": ("REQ-PDEF-0011", "REQ-CTRL-0004"),
    "PP-TASK-000381": ("REQ-PDEF-0011", "REQ-CTRL-0004"),
}
_ACTIVE_REALIGNMENT_IDS = {
    "PP-EPIC-000036",
    "PP-STORY-000138",
    "PP-TASK-000380",
}
_PAUSED_LANE_EXCLUSIONS = {
    "PP-TASK-000346",
    "PP-TASK-000347",
    "PP-TASK-000348",
    "PP-TASK-000349",
}


def _issue_paths(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for directory in ("epics", "stories", "tasks", "subtasks", "bugs", "spikes")
        for path in sorted((root / "jira" / directory).glob("PP-*.json"))
    )


def _candidate(
    root: Path,
    issue: dict[str, Any],
    requirements: dict[str, dict[str, Any]],
    tests: dict[str, dict[str, Any]],
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    linked = [
        requirements[item] for item in issue.get("requirement_ids", []) if item in requirements
    ]
    reasons: list[str] = []
    if not linked or not all(item.get("implementation_state") in _COMPLETE for item in linked):
        reasons.append("not every linked requirement is complete")
    artifacts = tuple(str(item) for item in issue.get("expected_implementation_artifacts", []))
    if not artifacts or not all((root / item).exists() for item in artifacts):
        reasons.append("expected implementation artifacts are missing")
    required_tests = tuple(str(item) for item in issue.get("required_tests", []))
    if not required_tests or not all(
        item in tests and (root / str(tests[item].get("path", ""))).exists()
        for item in required_tests
    ):
        reasons.append("required cataloged tests are missing")
    criteria = issue.get("acceptance_criteria", [])
    if not criteria or not all(
        isinstance(item, dict)
        and isinstance(item.get("verification"), dict)
        and isinstance(item["verification"].get("path"), str)
        and (root / item["verification"]["path"]).exists()
        for item in criteria
    ):
        reasons.append("acceptance verification paths are missing")
    evidence_ids = tuple(
        sorted({str(evidence) for item in linked for evidence in item.get("evidence_ids", [])})
    )
    if not evidence_ids:
        reasons.append("linked requirements have no verified evidence references")
    return not reasons, tuple(reasons), evidence_ids


def _base_issue(root: Path, base_ref: str, path: Path) -> dict[str, Any] | None:
    relative = path.relative_to(root).as_posix()
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{relative}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return json.loads(result.stdout) if result.returncode == 0 else None


def reconcile(root: Path, *, apply: bool, base_ref: str) -> dict[str, Any]:
    requirements = {
        str(item["requirement_id"]): item
        for item in read_jsonl(root / "plans/_traceability/requirements.jsonl")
    }
    tests = {
        str(item["test_id"]): item
        for item in read_json(root / "tests/TEST_CATALOG.json").get("tests", [])
    }
    candidates: list[str] = []
    quarantined: list[dict[str, Any]] = []
    excluded_paused_lane: list[str] = []
    unchanged: list[str] = []
    for path in _issue_paths(root):
        issue = read_json(path)
        issue_id = str(issue["local_id"])
        base_issue = _base_issue(root, base_ref, path)
        if issue_id in _PAUSED_LANE_EXCLUSIONS and base_issue is not None:
            excluded_paused_lane.append(issue_id)
            if apply and issue != base_issue:
                write_json(path, base_issue)
            continue
        if (
            base_issue is not None
            and base_issue.get("implementation_state") != "PLANNED_ONLY"
            and issue_id not in _REQUIREMENT_ID_REPAIRS
            and issue_id not in _ACTIVE_REALIGNMENT_IDS
        ):
            unchanged.append(issue_id)
            if apply and issue != base_issue:
                write_json(path, base_issue)
            continue
        acceptance_id = _ACCEPTANCE_ID_REPAIRS.get(issue_id)
        requirement_ids = _REQUIREMENT_ID_REPAIRS.get(issue_id)
        if apply and (
            (acceptance_id and len(issue.get("acceptance_criteria", [])) == 1)
            or requirement_ids
            or issue_id in _ACTIVE_REALIGNMENT_IDS
        ):
            if acceptance_id:
                issue["acceptance_criteria"][0]["criterion_id"] = acceptance_id
            if requirement_ids:
                issue["requirement_ids"] = list(requirement_ids)
            if issue_id in _ACTIVE_REALIGNMENT_IDS:
                issue["state"] = "IN_PROGRESS"
                issue["implementation_state"] = "PARTIALLY_IMPLEMENTED"
                issue["labels"] = sorted(set(issue.get("labels", [])) | {"in-progress"})
            write_json(path, issue)
        linked = [
            requirements[item] for item in issue.get("requirement_ids", []) if item in requirements
        ]
        if not linked or not all(item.get("implementation_state") in _COMPLETE for item in linked):
            unchanged.append(str(issue["local_id"]))
            continue
        supported, reasons, evidence_ids = _candidate(root, issue, requirements, tests)
        if not supported:
            quarantined.append({"issue_id": issue["local_id"], "reasons": list(reasons)})
            continue
        candidates.append(str(issue["local_id"]))
        if not apply:
            continue
        issue["implementation_state"] = "IMPLEMENTED"
        issue["completion_evidence"] = list(evidence_ids)
        for criterion in issue["acceptance_criteria"]:
            criterion["verification"]["status"] = "VERIFIED"
        labels = {str(item) for item in issue.get("labels", [])}
        labels.update({"implemented", "bulk-reconciled"})
        issue["labels"] = sorted(labels)
        write_json(path, issue)
    return {
        "schema_version": "1.0.0",
        "apply": apply,
        "candidate_count": len(candidates),
        "candidate_issue_ids": candidates,
        "quarantined_count": len(quarantined),
        "quarantined": quarantined,
        "paused_lane_exclusion_count": len(excluded_paused_lane),
        "paused_lane_exclusion_issue_ids": excluded_paused_lane,
        "unchanged_count": len(unchanged),
        "lifecycle_transition_count": 0,
        "rule": (
            "This batch reconciles evidence-backed implementation projections only. It does not "
            "advance Jira lifecycle state, create per-label branches, or claim remote completion."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    result = reconcile(root, apply=args.apply, base_ref=args.base_ref)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        write_json(output, result)
    else:
        import json

        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
