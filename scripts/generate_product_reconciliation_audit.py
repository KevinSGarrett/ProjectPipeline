from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl, write_json
from project_pipeline.control.kernel import issue_has_reconciliation_evidence


def _issues(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for directory in ("epics", "stories", "tasks", "subtasks", "bugs"):
        for path in sorted((root / "jira" / directory).glob("*.json")):
            issue = read_json(path)
            result[str(issue["local_id"])] = issue
    return result


def build_audit(root: Path) -> dict[str, object]:
    issues = _issues(root)
    requirements = read_jsonl(root / "plans/_traceability/requirements.jsonl")
    implemented = [
        item for item in requirements if item.get("implementation_state") == "IMPLEMENTED"
    ]
    findings: list[dict[str, object]] = []
    for requirement in implemented:
        linked = [
            issues[issue_id] for issue_id in requirement.get("jira_ids", []) if issue_id in issues
        ]
        if not linked or not all(
            item.get("implementation_state") == "PLANNED_ONLY" for item in linked
        ):
            continue
        findings.append(
            {
                "requirement_id": requirement["requirement_id"],
                "issue_ids": sorted(str(item["local_id"]) for item in linked),
                "status": "RECONCILIATION_REQUIRED",
                "reason": (
                    "Requirement implementation is evidenced, but every linked source Jira item "
                    "still projects PLANNED_ONLY. Bulk source/database/generated/remote "
                    "reconciliation is required before Control may treat the work as fresh "
                    "implementation or the finding may close."
                ),
            }
        )
    issue_findings: list[dict[str, object]] = []
    complete_states = {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED", "BLOCKED_EXTERNAL"}
    requirements_by_id = {str(item["requirement_id"]): item for item in requirements}
    for issue in issues.values():
        linked = [
            requirements_by_id[item]
            for item in issue.get("requirement_ids", [])
            if item in requirements_by_id
        ]
        if issue.get("implementation_state") in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"}:
            continue
        has_complete_requirements = bool(linked) and all(
            item.get("implementation_state") in complete_states for item in linked
        )
        has_existing_delivery = issue_has_reconciliation_evidence(root, issue)
        if not has_complete_requirements and not has_existing_delivery:
            continue
        issue_findings.append(
            {
                "issue_id": issue["local_id"],
                "status": "ISSUE_SPECIFIC_AUDIT_REQUIRED",
                "reason": (
                    "Requirement state or the issue's own artifacts, tests, criteria, and evidence "
                    "indicate existing delivery. Control must quarantine it from fresh "
                    "implementation selection until an issue-specific missing delta is established "
                    "or the canonical Jira projection is reconciled."
                ),
                "existing_delivery_footprint": has_existing_delivery,
                "all_linked_requirements_complete": has_complete_requirements,
            }
        )
    return {
        "schema_version": "1.0.0",
        "audit_id": "IMPLEMENTED-REQUIREMENT-JIRA-AUDIT-001",
        "status": "OPEN",
        "implemented_requirement_count": len(implemented),
        "reconciliation_required_count": len(findings),
        "findings": findings,
        "issue_specific_audit_count": len(issue_findings),
        "issue_findings": issue_findings,
        "closure_rule": (
            "A finding closes only after issue-specific implementation, tests, criteria, and "
            "evidence are checked and canonical Jira source, Control database, generated views, "
            "and observed remote state are deliberately reconciled in a compatible batch."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("plans/reconciliation/IMPLEMENTED_REQUIREMENT_JIRA_AUDIT.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    write_json(output, build_audit(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
