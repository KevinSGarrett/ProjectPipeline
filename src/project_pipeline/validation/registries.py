from __future__ import annotations

import json
import re
from collections import Counter, defaultdict, deque
from itertools import pairwise
from pathlib import Path
from typing import Any

from project_pipeline.ids import (
    ACCEPTANCE_ID,
    DECISION_ID,
    ISSUE_ID,
    PLAN_ID,
    REQUIREMENT_ID,
    SOURCE_REFERENCE,
)
from project_pipeline.io import (
    iter_repository_files,
    read_json,
    read_jsonl,
    sha256_canonical_file,
)
from project_pipeline.jira import build_relationship_edges
from project_pipeline.validation.models import ValidationReport

IMPLEMENTATION_STATES = {
    "IMPLEMENTED",
    "PARTIALLY_IMPLEMENTED",
    "MOCK_VERIFIED",
    "LIVE_VERIFIED",
    "BLOCKED_EXTERNAL",
    "PLANNED_ONLY",
}
UPSTREAM_DISPOSITIONS = {
    "ADOPT_DEPENDENCY",
    "ADAPT_COMPONENT",
    "MINE_ARCHITECTURE",
    "MINE_IMPLEMENTATION_PATTERN",
    "MINE_TEST_PATTERN",
    "EVALUATE_LATER",
    "REJECT",
    "NOT_RELEVANT",
}
_PLAN_STATUS = re.compile(
    r"(?im)^(?:"
    r"\s*(?:-\s*)?\*\*(?:Status|Implementation status|Plan status):\*\*\s*`?([A-Z_]+)`?\s*"
    r"|#\s+PLAN-[A-Z]+-[0-9]{3}\b.*\[Status:\s*([A-Z_]+)\]\s*"
    r")$"
)


def check_json_documents(root: Path, report: ValidationReport) -> None:
    for path in iter_repository_files(root):
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                report.add("ERROR", "JSON001", f"Invalid JSON: {error}", relative)
        elif path.suffix.lower() == ".jsonl":
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as error:
                    report.add("ERROR", "JSONL001", f"Invalid JSONL: {error}", relative, number)


def check_plan_registry(root: Path, report: ValidationReport) -> tuple[set[str], dict[str, Any]]:
    catalog_path = root / "plans" / "PLAN_CATALOG.json"
    section_path = root / "plans" / "_indexes" / "plan_section_index.json"
    if not catalog_path.exists() or not section_path.exists():
        report.add("ERROR", "PLAN000", "Plan catalog or section index is missing", "plans")
        return set(), {}
    catalog = read_json(catalog_path)
    section_index = read_json(section_path)
    plan_ids: set[str] = set()
    for entry in catalog.get("plans", []):
        plan_id = entry.get("plan_id", "")
        if not PLAN_ID.fullmatch(plan_id):
            report.add("ERROR", "PLAN001", f"Invalid plan ID: {plan_id}", "plans/PLAN_CATALOG.json")
            continue
        if plan_id in plan_ids:
            report.add(
                "ERROR", "PLAN002", f"Duplicate plan ID: {plan_id}", "plans/PLAN_CATALOG.json"
            )
        plan_ids.add(plan_id)
        relative = entry.get("path", "")
        path = root / relative
        if not path.exists():
            report.add(
                "ERROR",
                "PLAN003",
                f"Plan path does not exist: {relative}",
                "plans/PLAN_CATALOG.json",
            )
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith(f"# {plan_id} "):
            report.add("ERROR", "PLAN004", "Plan heading does not match catalog ID", relative, 1)
        status_match = _PLAN_STATUS.search(text)
        plan_status: str | None = None
        if status_match is None:
            report.add("ERROR", "PLAN012", "Plan has no authoritative status metadata", relative)
        else:
            plan_status = next(group for group in status_match.groups() if group).upper()
        if plan_status is not None and plan_status != str(entry.get("status", "")).upper():
            report.add(
                "ERROR",
                "PLAN013",
                (
                    f"Plan status {plan_status} does not match catalog "
                    f"status {str(entry.get('status', '')).upper()}"
                ),
                relative,
            )
        sections = re.findall(r"^##\s+([A-Z0-9-]+:SEC-[0-9]{2})\b", text, flags=re.MULTILINE)
        if not sections:
            report.add("ERROR", "PLAN005", "Plan has no stable section IDs", relative)
        for section in sections:
            if not section.startswith(plan_id + ":"):
                report.add(
                    "ERROR", "PLAN006", f"Section belongs to another plan: {section}", relative
                )
            if section not in section_index:
                report.add(
                    "ERROR", "PLAN007", f"Section missing from generated index: {section}", relative
                )
        line_path = root / "plans" / "_line_numbered" / f"{path.stem}.lines.txt"
        if not line_path.exists():
            report.add("ERROR", "PLAN008", "Line-numbered representation is missing", relative)
        else:
            source_lines = text.splitlines()
            numbered_lines = line_path.read_text(encoding="utf-8").splitlines()
            expected = [f"L{number:06d} | {line}" for number, line in enumerate(source_lines, 1)]
            if numbered_lines != expected:
                report.add(
                    "ERROR",
                    "PLAN009",
                    "Line-numbered representation is stale",
                    line_path.relative_to(root).as_posix(),
                )
        for source in entry.get("source_references", []):
            if not SOURCE_REFERENCE.fullmatch(source):
                report.add(
                    "ERROR",
                    "PLAN010",
                    f"Invalid source reference: {source}",
                    "plans/PLAN_CATALOG.json",
                )
    indexed_plan_ids = {value.get("plan_id") for value in section_index.values()}
    for missing in sorted(plan_ids - indexed_plan_ids):
        report.add(
            "ERROR",
            "PLAN011",
            f"Plan has no indexed sections: {missing}",
            "plans/_indexes/plan_section_index.json",
        )
    return plan_ids, section_index


def load_issues(root: Path, report: ValidationReport) -> dict[str, dict[str, Any]]:
    index_path = root / "jira" / "indexes" / "issues.jsonl"
    if not index_path.exists():
        report.add("ERROR", "JIRA000", "Jira issue index is missing", "jira/indexes/issues.jsonl")
        return {}
    issues: dict[str, dict[str, Any]] = {}
    for issue in read_jsonl(index_path):
        issue_id = issue.get("local_id", "")
        if issue_id in issues:
            report.add(
                "ERROR", "JIRA001", f"Duplicate issue ID: {issue_id}", "jira/indexes/issues.jsonl"
            )
        issues[issue_id] = issue
    return issues


def _has_cycle(edges: dict[str, set[str]]) -> bool:
    indegree: dict[str, int] = defaultdict(int)
    nodes = set(edges)
    for source, targets in edges.items():
        nodes.update(targets)
        for target in targets:
            indegree[target] += 1
        indegree.setdefault(source, indegree.get(source, 0))
    queue = deque(node for node in nodes if indegree[node] == 0)
    observed = 0
    while queue:
        node = queue.popleft()
        observed += 1
        for target in edges.get(node, set()):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return observed != len(nodes)


def check_jira_registry(
    root: Path,
    report: ValidationReport,
    plan_ids: set[str],
    section_index: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    issues = load_issues(root, report)
    required = {
        "local_id",
        "issue_type",
        "title",
        "parent",
        "objective",
        "rationale",
        "description",
        "scope",
        "exclusions",
        "requirement_ids",
        "source_references",
        "plan_references",
        "dependencies",
        "blockers",
        "relationships",
        "expected_implementation_artifacts",
        "expected_file_locations",
        "acceptance_criteria",
        "definition_of_done",
        "required_tests",
        "evidence_required",
        "risk_classification",
        "security_impact",
        "observability_impact",
        "rollback_recovery_consideration",
        "owner_required_capability",
        "labels",
        "state",
        "implementation_state",
        "completion_evidence",
    }
    acceptance_ids: set[str] = set()
    child_counts: dict[str, int] = defaultdict(int)
    dependency_edges: dict[str, set[str]] = defaultdict(set)
    directory = {
        "EPIC": "epics",
        "STORY": "stories",
        "TASK": "tasks",
        "SUBTASK": "subtasks",
        "BUG": "bugs",
        "SPIKE": "spikes",
    }
    for issue_id, issue in issues.items():
        relative = f"jira/{directory.get(issue.get('issue_type'), 'unknown')}/{issue_id}.json"
        if not ISSUE_ID.fullmatch(issue_id):
            report.add(
                "ERROR", "JIRA002", f"Invalid issue ID: {issue_id}", "jira/indexes/issues.jsonl"
            )
        missing = sorted(required - issue.keys())
        if missing:
            report.add("ERROR", "JIRA003", f"Missing required fields: {missing}", relative)
        if issue.get("implementation_state") not in IMPLEMENTATION_STATES:
            report.add("ERROR", "JIRA004", "Invalid implementation state", relative)
        issue_path = root / relative
        if not issue_path.exists():
            report.add("ERROR", "JIRA005", "Indexed issue file is missing", relative)
        else:
            stored = read_json(issue_path)
            if stored != issue:
                report.add("ERROR", "JIRA006", "Issue index and issue file differ", relative)
        parent = issue.get("parent")
        if parent:
            if parent not in issues:
                report.add("ERROR", "JIRA007", f"Parent does not exist: {parent}", relative)
            else:
                child_counts[parent] += 1
                allowed = {
                    "STORY": {"EPIC"},
                    "TASK": {"STORY", "EPIC"},
                    "SUBTASK": {"TASK"},
                    "BUG": {"STORY", "EPIC"},
                    "SPIKE": {"STORY", "EPIC"},
                }
                parent_type = issues[parent].get("issue_type")
                if parent_type not in allowed.get(issue.get("issue_type"), set()):
                    report.add("ERROR", "JIRA008", f"Invalid parent type {parent_type}", relative)
        elif issue.get("issue_type") != "EPIC":
            report.add("ERROR", "JIRA009", "Non-epic issue has no parent", relative)
        for dependency in issue.get("dependencies", []):
            if dependency not in issues:
                report.add("ERROR", "JIRA010", f"Dependency does not exist: {dependency}", relative)
            elif dependency == issue_id:
                report.add("ERROR", "JIRA011", "Issue depends on itself", relative)
            else:
                dependency_edges[issue_id].add(dependency)
        for source in issue.get("source_references", []):
            if not SOURCE_REFERENCE.fullmatch(source):
                report.add("ERROR", "JIRA012", f"Invalid source reference: {source}", relative)
        for plan_ref in issue.get("plan_references", []):
            plan_id = plan_ref.get("plan_id")
            section_id = plan_ref.get("section_id")
            if plan_id not in plan_ids:
                report.add("ERROR", "JIRA013", f"Unknown plan ID: {plan_id}", relative)
            if section_id not in section_index:
                report.add("ERROR", "JIRA014", f"Unknown plan section: {section_id}", relative)
            elif plan_ref.get("line_reference") != section_index[section_id].get("line_reference"):
                report.add("ERROR", "JIRA015", f"Stale plan line reference: {section_id}", relative)
        criteria = issue.get("acceptance_criteria", [])
        if not criteria:
            report.add("ERROR", "JIRA016", "Issue has no acceptance criteria", relative)
        for criterion in criteria:
            criterion_id = criterion.get("criterion_id", "")
            if not ACCEPTANCE_ID.fullmatch(criterion_id):
                report.add("ERROR", "JIRA017", f"Invalid acceptance ID: {criterion_id}", relative)
            if criterion_id in acceptance_ids:
                report.add("ERROR", "JIRA018", f"Duplicate acceptance ID: {criterion_id}", relative)
            acceptance_ids.add(criterion_id)
            verification = criterion.get("verification", {})
            if not all(
                verification.get(field) for field in ("method", "path", "command", "status")
            ):
                report.add(
                    "ERROR", "JIRA019", f"Incomplete verification for {criterion_id}", relative
                )
        if issue.get("state") == "DONE" and not issue.get("completion_evidence"):
            report.add("ERROR", "JIRA020", "Completed issue lacks completion evidence", relative)
        context_path = root / "jira" / "source_context" / f"{issue_id}.md"
        if not context_path.exists():
            report.add("ERROR", "JIRA021", "Issue source-context file is missing", relative)
    for issue_id, issue in issues.items():
        if (
            issue.get("issue_type") == "EPIC"
            and child_counts[issue_id] == 0
            and issue.get("state") != "CANCELLED"
        ):
            report.add(
                "ERROR", "JIRA022", "Orphan epic has no child", f"jira/epics/{issue_id}.json"
            )
    if _has_cycle(dependency_edges):
        report.add(
            "ERROR", "JIRA023", "Dependency graph contains a cycle", "jira/relationships/graph.json"
        )

    expected_edges = build_relationship_edges(issues.values())

    graph_path = root / "jira" / "relationships" / "graph.json"
    if not graph_path.exists():
        report.add(
            "ERROR", "JIRA024", "Relationship graph is missing", "jira/relationships/graph.json"
        )
    else:
        graph = read_json(graph_path)
        graph_nodes = {node.get("id") for node in graph.get("nodes", [])}
        if graph_nodes != set(issues):
            report.add(
                "ERROR",
                "JIRA025",
                "Graph nodes do not match issue index",
                "jira/relationships/graph.json",
            )
        for edge in graph.get("edges", []):
            if edge.get("from") not in issues or edge.get("to") not in issues:
                report.add(
                    "ERROR",
                    "JIRA026",
                    f"Dangling graph edge: {edge}",
                    "jira/relationships/graph.json",
                )
        if graph.get("node_count") != len(issues):
            report.add(
                "ERROR", "JIRA028", "Graph node count is stale", "jira/relationships/graph.json"
            )
        if graph.get("edge_count") != len(expected_edges):
            report.add(
                "ERROR", "JIRA029", "Graph edge count is stale", "jira/relationships/graph.json"
            )
        if graph.get("edges") != expected_edges:
            report.add(
                "ERROR",
                "JIRA030",
                "Graph edges differ from authoritative issue records",
                "jira/relationships/graph.json",
            )
        expected_nodes = [
            {
                "id": issue["local_id"],
                "type": issue["issue_type"],
                "state": issue["state"],
                "title": issue["title"],
            }
            for issue in sorted(
                issues.values(),
                key=lambda item: (int(item["local_id"].rsplit("-", 1)[1]), item["local_id"]),
            )
        ]
        if graph.get("nodes") != expected_nodes:
            report.add(
                "ERROR",
                "JIRA031",
                "Graph nodes are stale or unsorted",
                "jira/relationships/graph.json",
            )

    relationship_index_path = root / "jira" / "relationships" / "issues.jsonl"
    if not relationship_index_path.exists():
        report.add(
            "ERROR",
            "JIRA032",
            "Relationship edge index is missing",
            "jira/relationships/issues.jsonl",
        )
    elif read_jsonl(relationship_index_path) != expected_edges:
        report.add(
            "ERROR",
            "JIRA033",
            "Relationship edge index differs from authoritative issue records",
            "jira/relationships/issues.jsonl",
        )

    by_id_path = root / "jira" / "indexes" / "issues_by_id.json"
    if not by_id_path.exists():
        report.add(
            "ERROR", "JIRA034", "Jira by-ID index is missing", "jira/indexes/issues_by_id.json"
        )
    elif read_json(by_id_path) != issues:
        report.add(
            "ERROR",
            "JIRA035",
            "Jira by-ID index differs from issue index",
            "jira/indexes/issues_by_id.json",
        )

    issue_type_order = ("BUG", "EPIC", "SPIKE", "STORY", "SUBTASK", "TASK")
    counts_by_type = Counter(issue.get("issue_type") for issue in issues.values())
    expected_type_counts = {kind: counts_by_type.get(kind, 0) for kind in issue_type_order}
    expected_state_counts = dict(
        sorted(Counter(issue.get("state") for issue in issues.values()).items())
    )
    manifest_path = root / "jira" / "BOARD_MANIFEST.json"
    if not manifest_path.exists():
        report.add("ERROR", "JIRA036", "Board manifest is missing", "jira/BOARD_MANIFEST.json")
    else:
        manifest = read_json(manifest_path)
        if manifest.get("issue_count") != len(issues):
            report.add("ERROR", "JIRA027", "Board issue count is stale", "jira/BOARD_MANIFEST.json")
        if manifest.get("counts_by_type") != expected_type_counts:
            report.add(
                "ERROR", "JIRA037", "Board type counts are stale", "jira/BOARD_MANIFEST.json"
            )
        if manifest.get("counts_by_state") != expected_state_counts:
            report.add(
                "ERROR", "JIRA038", "Board state counts are stale", "jira/BOARD_MANIFEST.json"
            )

    status_path = root / "jira" / "reports" / "backlog_status.json"
    if not status_path.exists():
        report.add(
            "ERROR",
            "JIRA039",
            "Backlog status report is missing",
            "jira/reports/backlog_status.json",
        )
    else:
        status = read_json(status_path)
        expected_status = {
            "schema_version": "1.0.0",
            "issue_count": len(issues),
            "counts_by_type": expected_type_counts,
            "counts_by_state": expected_state_counts,
            "requirements_referenced": len(
                {
                    requirement_id
                    for issue in issues.values()
                    for requirement_id in issue.get("requirement_ids", [])
                }
            ),
            "edge_count": len(expected_edges),
        }
        if status != expected_status:
            report.add(
                "ERROR",
                "JIRA040",
                "Backlog status report is stale",
                "jira/reports/backlog_status.json",
            )
    return issues


def check_requirement_registry(
    root: Path,
    report: ValidationReport,
    plan_ids: set[str],
    issues: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    path = root / "plans" / "_traceability" / "requirements.jsonl"
    if not path.exists():
        report.add(
            "ERROR", "REQ000", "Requirement registry is missing", path.relative_to(root).as_posix()
        )
        return {}
    requirements: dict[str, dict[str, Any]] = {}
    evidence_ids: set[str] = set()
    evidence_path = root / "evidence" / "EVIDENCE_LEDGER.jsonl"
    if evidence_path.exists():
        evidence_ids = {row.get("evidence_id") for row in read_jsonl(evidence_path)}
    for item in read_jsonl(path):
        requirement_id = item.get("requirement_id", "")
        if not REQUIREMENT_ID.fullmatch(requirement_id):
            report.add(
                "ERROR",
                "REQ001",
                f"Invalid requirement ID: {requirement_id}",
                path.relative_to(root).as_posix(),
            )
        if requirement_id in requirements:
            report.add(
                "ERROR",
                "REQ002",
                f"Duplicate requirement ID: {requirement_id}",
                path.relative_to(root).as_posix(),
            )
        requirements[requirement_id] = item
        if item.get("implementation_state") not in IMPLEMENTATION_STATES:
            report.add(
                "ERROR", "REQ003", "Invalid implementation state", path.relative_to(root).as_posix()
            )
        if not item.get("statement"):
            report.add(
                "ERROR",
                "REQ004",
                "Requirement statement is empty",
                path.relative_to(root).as_posix(),
            )
        for source in item.get("source_references", []):
            if not SOURCE_REFERENCE.fullmatch(source):
                report.add(
                    "ERROR",
                    "REQ005",
                    f"Invalid source reference: {source}",
                    path.relative_to(root).as_posix(),
                )
        for plan_id in item.get("plan_ids", []):
            if plan_id not in plan_ids:
                report.add(
                    "ERROR",
                    "REQ006",
                    f"Unknown plan ID: {plan_id}",
                    path.relative_to(root).as_posix(),
                )
        for issue_id in item.get("jira_ids", []):
            if issue_id not in issues:
                report.add(
                    "ERROR",
                    "REQ007",
                    f"Unknown Jira ID: {issue_id}",
                    path.relative_to(root).as_posix(),
                )
        for implementation_path in item.get("implementation_paths", []):
            if not (root / implementation_path).exists():
                report.add(
                    "ERROR",
                    "REQ008",
                    f"Implementation path does not exist: {implementation_path}",
                    path.relative_to(root).as_posix(),
                )
        for evidence_id in item.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                report.add(
                    "ERROR",
                    "REQ009",
                    f"Unknown evidence ID: {evidence_id}",
                    path.relative_to(root).as_posix(),
                )
        if item.get("implementation_state") in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"}:
            for field, code in (
                ("implementation_paths", "REQ010"),
                ("test_ids", "REQ011"),
                ("evidence_ids", "REQ012"),
            ):
                if not item.get(field):
                    report.add(
                        "ERROR",
                        code,
                        f"Implemented requirement has no {field}",
                        path.relative_to(root).as_posix(),
                    )
    for issue_id, issue in issues.items():
        relative = "jira/indexes/issues.jsonl"
        for requirement_id in issue.get("requirement_ids", []):
            if requirement_id not in requirements:
                report.add(
                    "ERROR",
                    "REQ013",
                    f"Issue {issue_id} references unknown requirement {requirement_id}",
                    relative,
                )
    return requirements


def check_traceability_exports(
    root: Path, report: ValidationReport, requirements: dict[str, dict[str, Any]]
) -> None:
    target = root / "plans" / "_traceability"
    mappings = {
        "requirements_to_plans.jsonl": "plan_ids",
        "requirements_to_jira.jsonl": "jira_ids",
        "requirements_to_implementation.jsonl": "implementation_paths",
        "requirements_to_tests.jsonl": "test_ids",
        "requirements_to_evidence.jsonl": "evidence_ids",
        "requirements_to_decisions.jsonl": "decision_ids",
        "requirements_to_open_decisions.jsonl": "open_decision_ids",
        "requirements_to_evolution.jsonl": "evolution_ids",
    }
    for filename, field in mappings.items():
        path = target / filename
        if not path.exists():
            report.add(
                "ERROR",
                "TRACE001",
                f"Traceability export is missing: {filename}",
                path.relative_to(root).as_posix(),
            )
            continue
        rows = read_jsonl(path)
        seen: set[str] = set()
        for row in rows:
            requirement_id = row.get("requirement_id")
            if requirement_id in seen:
                report.add(
                    "ERROR",
                    "TRACE002",
                    f"Duplicate requirement in {filename}: {requirement_id}",
                    path.relative_to(root).as_posix(),
                )
            seen.add(requirement_id)
            if requirement_id not in requirements:
                report.add(
                    "ERROR",
                    "TRACE003",
                    f"Unknown requirement in {filename}: {requirement_id}",
                    path.relative_to(root).as_posix(),
                )
                continue
            if row.get(field, []) != requirements[requirement_id].get(field, []):
                report.add(
                    "ERROR",
                    "TRACE004",
                    f"Stale mapping for {requirement_id} in {filename}",
                    path.relative_to(root).as_posix(),
                )
        if seen != set(requirements):
            report.add(
                "ERROR",
                "TRACE005",
                f"{filename} does not cover every requirement",
                path.relative_to(root).as_posix(),
            )

    source_path = target / "source_to_requirements.jsonl"
    expected: dict[str, list[str]] = defaultdict(list)
    for requirement_id, item in requirements.items():
        for reference in item.get("source_references", []):
            expected[reference].append(requirement_id)
    expected_rows = [
        {"source_reference": reference, "requirement_ids": sorted(requirement_ids)}
        for reference, requirement_ids in sorted(expected.items())
    ]
    if not source_path.exists():
        report.add(
            "ERROR",
            "TRACE006",
            "Source-to-requirements export is missing",
            source_path.relative_to(root).as_posix(),
        )
    elif read_jsonl(source_path) != expected_rows:
        report.add(
            "ERROR",
            "TRACE007",
            "Source-to-requirements export is stale",
            source_path.relative_to(root).as_posix(),
        )


def check_adr_registry(root: Path, report: ValidationReport) -> None:
    path = root / "adr" / "ADR_CATALOG.json"
    if not path.exists():
        report.add("ERROR", "ADR000", "ADR catalog is missing", "adr/ADR_CATALOG.json")
        return
    seen: set[str] = set()
    for item in read_json(path).get("decisions", []):
        decision_id = item.get("decision_id", "")
        if not DECISION_ID.fullmatch(decision_id):
            report.add(
                "ERROR", "ADR001", f"Invalid decision ID: {decision_id}", "adr/ADR_CATALOG.json"
            )
        if decision_id in seen:
            report.add(
                "ERROR", "ADR002", f"Duplicate decision ID: {decision_id}", "adr/ADR_CATALOG.json"
            )
        seen.add(decision_id)
        decision_path = root / item.get("path", "")
        if not decision_path.exists():
            report.add(
                "ERROR",
                "ADR003",
                f"Decision file is missing: {item.get('path')}",
                "adr/ADR_CATALOG.json",
            )
        elif not decision_path.read_text(encoding="utf-8").startswith(f"# {decision_id} "):
            report.add(
                "ERROR", "ADR004", "Decision heading does not match catalog", item.get("path")
            )


def check_upstream_registry(root: Path, report: ValidationReport) -> None:
    path = root / "provenance" / "upstream_registry.json"
    if not path.exists():
        report.add(
            "ERROR",
            "UPSTREAM000",
            "Upstream registry is missing",
            path.relative_to(root).as_posix(),
        )
        return
    registry = read_json(path)
    entries = registry.get("entries", [])
    if registry.get("entry_count") != len(entries):
        report.add(
            "ERROR",
            "UPSTREAM001",
            "Upstream entry count is stale",
            path.relative_to(root).as_posix(),
        )
    urls: set[str] = set()
    for entry in entries:
        url = entry.get("canonical_url", "")
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+", url):
            report.add(
                "ERROR",
                "UPSTREAM002",
                f"Invalid GitHub URL: {url}",
                path.relative_to(root).as_posix(),
            )
        if url in urls:
            report.add(
                "ERROR",
                "UPSTREAM003",
                f"Duplicate upstream URL: {url}",
                path.relative_to(root).as_posix(),
            )
        urls.add(url)
        if entry.get("disposition") not in UPSTREAM_DISPOSITIONS:
            report.add(
                "ERROR",
                "UPSTREAM004",
                f"Invalid disposition for {url}",
                path.relative_to(root).as_posix(),
            )
        if (
            entry.get("license") == "UNKNOWN_NOT_INSPECTED"
            and entry.get("incorporation_allowed") is not False
        ):
            report.add(
                "ERROR",
                "UPSTREAM005",
                f"Unknown-license source is marked incorporable: {url}",
                path.relative_to(root).as_posix(),
            )
    if registry.get("catalog_review_complete"):
        remaining = [
            entry.get("upstream_id")
            for entry in entries
            if entry.get("disposition") == "EVALUATE_LATER"
        ]
        if remaining:
            report.add(
                "ERROR",
                "UPSTREAM006",
                f"Catalog convergence marked complete with unresolved entries: {remaining}",
                path.relative_to(root).as_posix(),
            )
        if registry.get("terminal_disposition_count") != len(entries):
            report.add(
                "ERROR",
                "UPSTREAM007",
                "Terminal disposition count is stale",
                path.relative_to(root).as_posix(),
            )


def check_evidence_ledger(root: Path, report: ValidationReport) -> None:
    path = root / "evidence" / "EVIDENCE_LEDGER.jsonl"
    if not path.exists():
        report.add(
            "ERROR", "EVID000", "Evidence ledger is missing", path.relative_to(root).as_posix()
        )
        return
    rows = read_jsonl(path)
    seen: set[str] = set()
    required_fields = {
        "schema_version",
        "evidence_id",
        "claim",
        "artifact_path",
        "sha256",
        "method",
        "environment",
        "observed_at_utc",
        "result",
        "verification_status",
        "requirement_ids",
        "criterion_ids",
        "supersedes",
    }
    for row in rows:
        evidence_id = row.get("evidence_id", "")
        if not re.fullmatch(r"EVID-[0-9]{6}", evidence_id):
            report.add(
                "ERROR",
                "EVID005",
                f"Invalid evidence ID: {evidence_id}",
                path.relative_to(root).as_posix(),
            )
        if evidence_id in seen:
            report.add(
                "ERROR",
                "EVID001",
                f"Duplicate evidence ID: {evidence_id}",
                path.relative_to(root).as_posix(),
            )
        seen.add(evidence_id)
        missing = sorted(required_fields - row.keys())
        if missing:
            report.add(
                "ERROR",
                "EVID006",
                f"Evidence record {evidence_id} lacks fields: {missing}",
                path.relative_to(root).as_posix(),
            )
        artifact_path = row.get("artifact_path", "")
        if (
            not artifact_path
            or Path(artifact_path).is_absolute()
            or ".." in Path(artifact_path).parts
        ):
            report.add(
                "ERROR",
                "EVID007",
                f"Unsafe evidence artifact path: {artifact_path}",
                path.relative_to(root).as_posix(),
            )
        artifact = root / artifact_path
        if not artifact.exists():
            report.add(
                "ERROR",
                "EVID002",
                f"Evidence artifact is missing: {artifact_path}",
                path.relative_to(root).as_posix(),
            )
        elif row.get("sha256") != sha256_canonical_file(artifact):
            report.add(
                "ERROR",
                "EVID003",
                f"Evidence digest is stale: {artifact_path}",
                path.relative_to(root).as_posix(),
            )
        if row.get("result") == "PASS" and row.get("verification_status") != "VERIFIED":
            report.add(
                "ERROR",
                "EVID004",
                f"Passing evidence is not verified: {evidence_id}",
                path.relative_to(root).as_posix(),
            )

    summary_path = root / "evidence" / "EVIDENCE_SUMMARY.json"
    if not summary_path.exists():
        report.add(
            "ERROR",
            "EVID008",
            "Evidence summary is missing",
            summary_path.relative_to(root).as_posix(),
        )
    else:
        observed = read_json(summary_path)
        expected = {
            "schema_version": "1.0.0",
            "record_count": len(rows),
            "verified_pass_count": sum(
                row.get("result") == "PASS" and row.get("verification_status") == "VERIFIED"
                for row in rows
            ),
            "live_external_verification_count": sum(
                (
                    row.get("environment") == "live_external_environment"
                    or str(row.get("environment", "")).endswith("live_qualification")
                )
                and row.get("verification_status") == "VERIFIED"
                for row in rows
            ),
            "note": "Verified live external qualifications are counted only when their evidence artifact and digest are current; unavailable capabilities remain explicit.",
        }
        if observed != expected:
            report.add(
                "ERROR",
                "EVID009",
                "Evidence summary is stale",
                summary_path.relative_to(root).as_posix(),
            )


REQUIREMENT_DOMAINS = {
    "PDEF",
    "REQ",
    "ARCH",
    "CTRL",
    "SCHED",
    "CTX",
    "AGENT",
    "GOV",
    "ASSURE",
    "SEC",
    "BUDGET",
    "RES",
    "UX",
    "OPS",
    "INFRA",
    "LIFE",
    "UPSTREAM",
    "REL",
}
REQUIREMENT_PRIORITIES = {"P0", "P1", "P2", "P3"}
REQUIREMENT_RISKS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
REQUIREMENT_DISPOSITIONS = {"ACCEPTED", "SUPERSEDED", "EXCLUDED", "REJECTED", "OPEN_DECISION"}
AUTHORITY_CLASSIFICATIONS = {
    "SOURCE_DERIVED",
    "ENGINEERING_INFERENCE",
    "ENGINEERING_PROPOSAL",
    "REQUIRED_IMPLEMENTATION_DETAIL",
    "OPEN_DECISION",
}
OPEN_DECISION_STATUSES = {"OPEN", "BLOCKED_EXTERNAL", "RESOLVED", "SUPERSEDED"}
SOURCE_SECTION_DISPOSITIONS = {
    "REQUIREMENT_LINKED",
    "DESIGN_RATIONALE",
    "SUPPORTING_EXAMPLE",
    "UPSTREAM_RESEARCH_CONTEXT",
    "USER_INTENT_CONTEXT",
    "OPEN_DECISION_CONTEXT",
    "DUPLICATE_SOURCE",
    "PREFIX_OVERLAP_SOURCE",
}
TEST_ID_PATTERN = re.compile(r"^TEST-[A-Z0-9-]+-[0-9]{3}$")
OPEN_DECISION_PATTERN = re.compile(r"^OPEN-DEC-[0-9]{4}$")
EVOLUTION_PATTERN = re.compile(r"^SOURCE-EVOLUTION-[0-9]{4}$")
SOURCE_SECTION_PATTERN = re.compile(r"^SRC-[0-9]{3}-SEC-[0-9]{3}$")


def _validate_exact_source_references(
    root: Path,
    report: ValidationReport,
    references: list[str],
    *,
    code: str,
    relative: str,
) -> None:
    from project_pipeline.source_references import validate_source_reference

    for reference in references:
        for message in validate_source_reference(root, reference):
            report.add("ERROR", code, message, relative)


def check_requirement_supporting_registries(
    root: Path,
    report: ValidationReport,
    requirements: dict[str, dict[str, Any]],
    plan_ids: set[str],
    section_index: dict[str, Any],
    issues: dict[str, dict[str, Any]],
) -> None:
    """Validate the detailed requirement catalog and its supporting registries."""

    from project_pipeline.requirement_views import validate_requirement_views
    from project_pipeline.requirements import summarize_requirements
    from project_pipeline.source_references import canonical_evidence_key, parse_source_reference

    trace = root / "plans" / "_traceability"
    required_fields = {
        "schema_version",
        "requirement_id",
        "domain",
        "title",
        "statement",
        "requirement_type",
        "normative_strength",
        "authority_classification",
        "source_references",
        "source_sequence",
        "rationale",
        "priority",
        "risk",
        "disposition",
        "disposition_reason",
        "implementation_state",
        "plan_ids",
        "plan_section_ids",
        "decision_ids",
        "open_decision_ids",
        "evolution_ids",
        "jira_ids",
        "implementation_paths",
        "test_ids",
        "evidence_ids",
        "verification_class",
        "verification_expectation",
        "acceptance_summary",
        "tags",
    }

    test_catalog_path = root / "tests" / "TEST_CATALOG.json"
    test_ids: set[str] = set()
    if not test_catalog_path.exists():
        report.add("ERROR", "REG001", "Test catalog is missing", "tests/TEST_CATALOG.json")
    else:
        test_catalog = read_json(test_catalog_path)
        tests = test_catalog.get("tests", [])
        if test_catalog.get("test_count") != len(tests):
            report.add("ERROR", "REG002", "Test catalog count is stale", "tests/TEST_CATALOG.json")
        for item in tests:
            test_id = item.get("test_id", "")
            if not TEST_ID_PATTERN.fullmatch(test_id):
                report.add(
                    "ERROR", "REG003", f"Invalid test ID: {test_id}", "tests/TEST_CATALOG.json"
                )
            if test_id in test_ids:
                report.add(
                    "ERROR", "REG004", f"Duplicate test ID: {test_id}", "tests/TEST_CATALOG.json"
                )
            test_ids.add(test_id)
            path = root / item.get("path", "")
            if not path.exists():
                report.add(
                    "ERROR",
                    "REG005",
                    f"Test path is missing: {item.get('path')}",
                    "tests/TEST_CATALOG.json",
                )
            if not item.get("callable"):
                report.add(
                    "ERROR",
                    "REG006",
                    f"Test callable is empty: {test_id}",
                    "tests/TEST_CATALOG.json",
                )

    adr_path = root / "adr" / "ADR_CATALOG.json"
    adr_ids = (
        {item.get("decision_id") for item in read_json(adr_path).get("decisions", [])}
        if adr_path.exists()
        else set()
    )

    decisions_path = root / "plans" / "01_requirements" / "open_decisions.jsonl"
    open_decisions: dict[str, dict[str, Any]] = {}
    if not decisions_path.exists():
        report.add(
            "ERROR",
            "REG007",
            "Open-decision registry is missing",
            decisions_path.relative_to(root).as_posix(),
        )
    else:
        for item in read_jsonl(decisions_path):
            decision_id = item.get("decision_id", "")
            if not OPEN_DECISION_PATTERN.fullmatch(decision_id):
                report.add(
                    "ERROR",
                    "REG008",
                    f"Invalid open-decision ID: {decision_id}",
                    decisions_path.relative_to(root).as_posix(),
                )
            if decision_id in open_decisions:
                report.add(
                    "ERROR",
                    "REG009",
                    f"Duplicate open-decision ID: {decision_id}",
                    decisions_path.relative_to(root).as_posix(),
                )
            open_decisions[decision_id] = item
            if item.get("status") not in OPEN_DECISION_STATUSES:
                report.add(
                    "ERROR",
                    "REG010",
                    f"Invalid open-decision status: {decision_id}",
                    decisions_path.relative_to(root).as_posix(),
                )
            for field in (
                "topic",
                "question",
                "options",
                "constraints",
                "resolution_method",
                "decision_gate",
            ):
                if not item.get(field):
                    report.add(
                        "ERROR",
                        "REG011",
                        f"Open decision {decision_id} lacks {field}",
                        decisions_path.relative_to(root).as_posix(),
                    )
            _validate_exact_source_references(
                root,
                report,
                item.get("source_references", []),
                code="REG012",
                relative=decisions_path.relative_to(root).as_posix(),
            )
            for plan_id in item.get("required_by_plan_ids", []):
                if plan_id not in plan_ids:
                    report.add(
                        "ERROR",
                        "REG013",
                        f"Open decision {decision_id} references unknown plan {plan_id}",
                        decisions_path.relative_to(root).as_posix(),
                    )
            linked = item.get("linked_requirement_ids", [])
            if not linked:
                report.add(
                    "ERROR",
                    "REG014",
                    f"Open decision {decision_id} has no linked requirements",
                    decisions_path.relative_to(root).as_posix(),
                )
            for requirement_id in linked:
                if requirement_id not in requirements:
                    report.add(
                        "ERROR",
                        "REG015",
                        f"Open decision {decision_id} links unknown requirement {requirement_id}",
                        decisions_path.relative_to(root).as_posix(),
                    )
                elif decision_id not in requirements[requirement_id].get("open_decision_ids", []):
                    report.add(
                        "ERROR",
                        "REG016",
                        f"Open decision {decision_id} reverse link is missing from {requirement_id}",
                        decisions_path.relative_to(root).as_posix(),
                    )

    evolution_path = root / "plans" / "01_requirements" / "source_evolution.jsonl"
    evolution: dict[str, dict[str, Any]] = {}
    if not evolution_path.exists():
        report.add(
            "ERROR",
            "REG017",
            "Source-evolution registry is missing",
            evolution_path.relative_to(root).as_posix(),
        )
    else:
        for item in read_jsonl(evolution_path):
            record_id = item.get("record_id", "")
            if not EVOLUTION_PATTERN.fullmatch(record_id):
                report.add(
                    "ERROR",
                    "REG018",
                    f"Invalid source-evolution ID: {record_id}",
                    evolution_path.relative_to(root).as_posix(),
                )
            if record_id in evolution:
                report.add(
                    "ERROR",
                    "REG019",
                    f"Duplicate source-evolution ID: {record_id}",
                    evolution_path.relative_to(root).as_posix(),
                )
            evolution[record_id] = item
            for field in ("relationship", "handling", "requirement_effect"):
                if not item.get(field):
                    report.add(
                        "ERROR",
                        "REG020",
                        f"Source evolution {record_id} lacks {field}",
                        evolution_path.relative_to(root).as_posix(),
                    )
            references = [*item.get("earlier_references", []), *item.get("later_references", [])]
            _validate_exact_source_references(
                root,
                report,
                references,
                code="REG021",
                relative=evolution_path.relative_to(root).as_posix(),
            )
            linked = item.get("linked_requirement_ids", [])
            if not linked:
                report.add(
                    "ERROR",
                    "REG022",
                    f"Source evolution {record_id} has no linked requirements",
                    evolution_path.relative_to(root).as_posix(),
                )
            for requirement_id in linked:
                if requirement_id not in requirements:
                    report.add(
                        "ERROR",
                        "REG023",
                        f"Source evolution {record_id} links unknown requirement {requirement_id}",
                        evolution_path.relative_to(root).as_posix(),
                    )
                elif record_id not in requirements[requirement_id].get("evolution_ids", []):
                    report.add(
                        "ERROR",
                        "REG024",
                        f"Source evolution {record_id} reverse link is missing from {requirement_id}",
                        evolution_path.relative_to(root).as_posix(),
                    )

    glossary_path = root / "plans" / "01_requirements" / "glossary.json"
    if not glossary_path.exists():
        report.add(
            "ERROR", "REG025", "Glossary is missing", glossary_path.relative_to(root).as_posix()
        )
    else:
        glossary = read_json(glossary_path)
        terms = glossary.get("terms", {})
        if glossary.get("term_count") != len(terms):
            report.add(
                "ERROR",
                "REG026",
                "Glossary term count is stale",
                glossary_path.relative_to(root).as_posix(),
            )
        for term, entry in terms.items():
            if not re.fullmatch(r"[a-z0-9_]+", term):
                report.add(
                    "ERROR",
                    "REG027",
                    f"Invalid glossary term key: {term}",
                    glossary_path.relative_to(root).as_posix(),
                )
            if not entry.get("definition"):
                report.add(
                    "ERROR",
                    "REG028",
                    f"Glossary term has no definition: {term}",
                    glossary_path.relative_to(root).as_posix(),
                )
            _validate_exact_source_references(
                root,
                report,
                entry.get("source_references", []),
                code="REG029",
                relative=glossary_path.relative_to(root).as_posix(),
            )

    for requirement_id, item in requirements.items():
        relative = "plans/_traceability/requirements.jsonl"
        missing = sorted(required_fields - item.keys())
        if missing:
            report.add(
                "ERROR", "REG030", f"Requirement {requirement_id} lacks fields {missing}", relative
            )
        if item.get("schema_version") != "2.0.0":
            report.add(
                "ERROR",
                "REG031",
                f"Requirement {requirement_id} has stale schema version",
                relative,
            )
        if item.get("domain") not in REQUIREMENT_DOMAINS:
            report.add(
                "ERROR", "REG032", f"Requirement {requirement_id} has invalid domain", relative
            )
        if item.get("priority") not in REQUIREMENT_PRIORITIES:
            report.add(
                "ERROR", "REG033", f"Requirement {requirement_id} has invalid priority", relative
            )
        if item.get("risk") not in REQUIREMENT_RISKS:
            report.add(
                "ERROR", "REG034", f"Requirement {requirement_id} has invalid risk", relative
            )
        if item.get("disposition") not in REQUIREMENT_DISPOSITIONS:
            report.add(
                "ERROR", "REG035", f"Requirement {requirement_id} has invalid disposition", relative
            )
        if item.get("authority_classification") not in AUTHORITY_CLASSIFICATIONS:
            report.add(
                "ERROR",
                "REG036",
                f"Requirement {requirement_id} has invalid authority classification",
                relative,
            )
        if item.get("normative_strength") not in {"SHALL", "SHOULD", "MAY"}:
            report.add(
                "ERROR",
                "REG037",
                f"Requirement {requirement_id} has invalid normative strength",
                relative,
            )
        if not item.get("disposition_reason") or not item.get("rationale"):
            report.add(
                "ERROR",
                "REG038",
                f"Requirement {requirement_id} lacks rationale or disposition reason",
                relative,
            )
        _validate_exact_source_references(
            root, report, item.get("source_references", []), code="REG039", relative=relative
        )
        evidence_keys = [
            canonical_evidence_key(root, value) for value in item.get("source_references", [])
        ]
        if len(evidence_keys) != len(set(evidence_keys)):
            report.add(
                "ERROR",
                "REG040",
                f"Requirement {requirement_id} double-counts duplicate source evidence",
                relative,
            )
        for section_id in item.get("plan_section_ids", []):
            if section_id not in section_index:
                report.add(
                    "ERROR",
                    "REG041",
                    f"Requirement {requirement_id} references unknown plan section {section_id}",
                    relative,
                )
        for decision_id in item.get("decision_ids", []):
            if decision_id not in adr_ids:
                report.add(
                    "ERROR",
                    "REG042",
                    f"Requirement {requirement_id} references unknown ADR {decision_id}",
                    relative,
                )
        for decision_id in item.get("open_decision_ids", []):
            if decision_id not in open_decisions:
                report.add(
                    "ERROR",
                    "REG043",
                    f"Requirement {requirement_id} references unknown open decision {decision_id}",
                    relative,
                )
        for record_id in item.get("evolution_ids", []):
            if record_id not in evolution:
                report.add(
                    "ERROR",
                    "REG044",
                    f"Requirement {requirement_id} references unknown source evolution {record_id}",
                    relative,
                )
        for test_id in item.get("test_ids", []):
            if test_id not in test_ids:
                report.add(
                    "ERROR",
                    "REG045",
                    f"Requirement {requirement_id} references unknown test {test_id}",
                    relative,
                )
        for issue_id in item.get("jira_ids", []):
            if issue_id in issues and requirement_id not in issues[issue_id].get(
                "requirement_ids", []
            ):
                report.add(
                    "ERROR",
                    "REG046",
                    f"Requirement {requirement_id} is missing from reverse Jira link {issue_id}",
                    relative,
                )

    expected_by_id = requirements
    by_id_path = trace / "requirements_by_id.json"
    if not by_id_path.exists() or read_json(by_id_path) != expected_by_id:
        report.add(
            "ERROR",
            "REG047",
            "requirements_by_id.json is stale",
            by_id_path.relative_to(root).as_posix(),
        )
    expected_by_domain: dict[str, list[str]] = defaultdict(list)
    expected_by_source: dict[str, list[str]] = defaultdict(list)
    for requirement_id, item in requirements.items():
        expected_by_domain[item["domain"]].append(requirement_id)
        for reference in item.get("source_references", []):
            expected_by_source[parse_source_reference(reference).source_id].append(requirement_id)
    expected_domain = {key: sorted(value) for key, value in sorted(expected_by_domain.items())}
    expected_source = {key: sorted(set(value)) for key, value in sorted(expected_by_source.items())}
    for filename, expected in (
        ("requirements_by_domain.json", expected_domain),
        ("requirements_by_source.json", expected_source),
    ):
        path = trace / filename
        if not path.exists() or read_json(path) != expected:
            report.add("ERROR", "REG048", f"{filename} is stale", path.relative_to(root).as_posix())
    expected_summary = summarize_requirements(requirements.values())
    expected_summary["by_state"] = expected_summary.pop("by_implementation_state")
    summary_path = trace / "requirement_registry_summary.json"
    if not summary_path.exists() or read_json(summary_path) != expected_summary:
        report.add(
            "ERROR",
            "REG049",
            "Requirement registry summary is stale",
            summary_path.relative_to(root).as_posix(),
        )

    evidence_path = root / "evidence" / "EVIDENCE_LEDGER.jsonl"
    evidence_ids = (
        {item.get("evidence_id") for item in read_jsonl(evidence_path)}
        if evidence_path.exists()
        else set()
    )
    for issue_id, issue in issues.items():
        relative = "jira/indexes/issues.jsonl"
        for test_id in issue.get("required_tests", []):
            if test_id not in test_ids:
                report.add(
                    "ERROR",
                    "REG050",
                    f"Jira issue {issue_id} references unknown test {test_id}",
                    relative,
                )
        for evidence_id in [
            *issue.get("evidence_required", []),
            *issue.get("completion_evidence", []),
        ]:
            if evidence_id not in evidence_ids:
                report.add(
                    "ERROR",
                    "REG051",
                    f"Jira issue {issue_id} references unknown evidence {evidence_id}",
                    relative,
                )

    for message in validate_requirement_views(root):
        report.add("ERROR", "REG052", message, "plans/01_requirements")


def check_source_section_registry(
    root: Path,
    report: ValidationReport,
    requirements: dict[str, dict[str, Any]],
) -> None:
    """Validate exhaustive section-level disposition of the canonical corpus."""

    from project_pipeline.section_coverage import source_section_summary
    from project_pipeline.source_references import parse_source_reference, validate_source_reference

    path = root / "plans" / "_traceability" / "source_sections.jsonl"
    if not path.exists():
        report.add(
            "ERROR",
            "SECTION000",
            "Source-section registry is missing",
            path.relative_to(root).as_posix(),
        )
        return
    rows = read_jsonl(path)
    pack = read_json(root / "provenance" / "source_pack_reference.json")
    expected_count = int(pack["statistics"]["section_count"])
    if len(rows) != expected_count:
        report.add(
            "ERROR",
            "SECTION001",
            f"Expected {expected_count} source sections, found {len(rows)}",
            path.relative_to(root).as_posix(),
        )
    metadata = read_json(root / "provenance" / "source_registry.json")
    source_metadata = {item["source_id"]: item for item in metadata["sources"]}
    decision_ids = {
        item.get("decision_id")
        for item in read_jsonl(root / "plans/01_requirements/open_decisions.jsonl")
    }
    evolution_ids = {
        item.get("record_id")
        for item in read_jsonl(root / "plans/01_requirements/source_evolution.jsonl")
    }
    seen: set[str] = set()
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        section_id = row.get("section_id", "")
        if not SOURCE_SECTION_PATTERN.fullmatch(section_id):
            report.add(
                "ERROR",
                "SECTION002",
                f"Invalid source-section ID: {section_id}",
                path.relative_to(root).as_posix(),
            )
        if section_id in seen:
            report.add(
                "ERROR",
                "SECTION003",
                f"Duplicate source-section ID: {section_id}",
                path.relative_to(root).as_posix(),
            )
        seen.add(section_id)
        source_id = row.get("source_id")
        by_source[source_id].append(row)
        if row.get("disposition") not in SOURCE_SECTION_DISPOSITIONS:
            report.add(
                "ERROR",
                "SECTION004",
                f"Invalid disposition for {section_id}",
                path.relative_to(root).as_posix(),
            )
        if not row.get("disposition_reason"):
            report.add(
                "ERROR",
                "SECTION005",
                f"Source section {section_id} lacks disposition reason",
                path.relative_to(root).as_posix(),
            )
        if not re.fullmatch(r"[0-9a-f]{64}", row.get("content_sha256", "")):
            report.add(
                "ERROR",
                "SECTION006",
                f"Invalid content digest for {section_id}",
                path.relative_to(root).as_posix(),
            )
        for message in validate_source_reference(root, row.get("source_reference", "")):
            report.add("ERROR", "SECTION007", message, path.relative_to(root).as_posix())
        try:
            reference = parse_source_reference(row.get("source_reference", ""))
        except ValueError:
            reference = None
        if reference and (reference.source_id, reference.start_line, reference.end_line) != (
            source_id,
            row.get("start_line"),
            row.get("end_line"),
        ):
            report.add(
                "ERROR",
                "SECTION008",
                f"Source-section range fields disagree for {section_id}",
                path.relative_to(root).as_posix(),
            )
        for requirement_id in row.get("requirement_ids", []):
            if requirement_id not in requirements:
                report.add(
                    "ERROR",
                    "SECTION009",
                    f"Source section {section_id} links unknown requirement {requirement_id}",
                    path.relative_to(root).as_posix(),
                )
                continue
            if reference:
                overlapping = False
                for value in requirements[requirement_id].get("source_references", []):
                    requirement_ref = parse_source_reference(value)
                    if (
                        requirement_ref.source_id == reference.source_id
                        and requirement_ref.start_line <= reference.end_line
                        and reference.start_line <= requirement_ref.end_line
                    ):
                        overlapping = True
                        break
                if not overlapping:
                    report.add(
                        "ERROR",
                        "SECTION010",
                        f"Source section {section_id} does not overlap linked requirement {requirement_id}",
                        path.relative_to(root).as_posix(),
                    )
        for decision_id in row.get("open_decision_ids", []):
            if decision_id not in decision_ids:
                report.add(
                    "ERROR",
                    "SECTION011",
                    f"Source section {section_id} links unknown open decision {decision_id}",
                    path.relative_to(root).as_posix(),
                )
        for evolution_id in row.get("evolution_ids", []):
            if evolution_id not in evolution_ids:
                report.add(
                    "ERROR",
                    "SECTION012",
                    f"Source section {section_id} links unknown evolution record {evolution_id}",
                    path.relative_to(root).as_posix(),
                )
    if set(by_source) != set(source_metadata):
        report.add(
            "ERROR",
            "SECTION013",
            "Source-section registry does not cover every canonical source",
            path.relative_to(root).as_posix(),
        )
    for source_id, source_rows in by_source.items():
        source_rows.sort(key=lambda item: item["ordinal"])
        expected_ordinal = list(range(1, len(source_rows) + 1))
        if [item["ordinal"] for item in source_rows] != expected_ordinal:
            report.add(
                "ERROR",
                "SECTION014",
                f"Source-section ordinals are not contiguous for {source_id}",
                path.relative_to(root).as_posix(),
            )
        if source_rows and source_rows[0]["start_line"] != 1:
            report.add(
                "ERROR",
                "SECTION015",
                f"Source-section coverage does not start at line 1 for {source_id}",
                path.relative_to(root).as_posix(),
            )
        for left, right in pairwise(source_rows):
            if right["start_line"] != left["end_line"] + 1:
                report.add(
                    "ERROR",
                    "SECTION016",
                    f"Source-section coverage has a gap or overlap for {source_id}",
                    path.relative_to(root).as_posix(),
                )
        if source_rows and source_rows[-1]["end_line"] != int(
            source_metadata[source_id]["line_count"]
        ):
            report.add(
                "ERROR",
                "SECTION017",
                f"Source-section coverage does not reach final line for {source_id}",
                path.relative_to(root).as_posix(),
            )
        expected_disposition = None
        if source_id == "SRC-018":
            expected_disposition = "DUPLICATE_SOURCE"
        elif source_id == "SRC-005":
            expected_disposition = "PREFIX_OVERLAP_SOURCE"
        if expected_disposition and {row["disposition"] for row in source_rows} != {
            expected_disposition
        }:
            report.add(
                "ERROR",
                "SECTION018",
                f"{source_id} is not consistently classified as {expected_disposition}",
                path.relative_to(root).as_posix(),
            )
    summary_path = root / "plans" / "_traceability" / "source_section_summary.json"
    expected_summary = source_section_summary(root)
    if not summary_path.exists() or read_json(summary_path) != expected_summary:
        report.add(
            "ERROR",
            "SECTION019",
            "Source-section summary is stale",
            summary_path.relative_to(root).as_posix(),
        )

    canonical_rows = defaultdict(list)
    for row in rows:
        canonical_rows[row["source_id"]].append((row["start_line"], row["end_line"]))
    for requirement_id, item in requirements.items():
        for value in item.get("source_references", []):
            reference = parse_source_reference(value)
            if not reference.source_id.startswith("SRC-"):
                continue
            if not any(
                start <= reference.end_line and reference.start_line <= end
                for start, end in canonical_rows[reference.source_id]
            ):
                report.add(
                    "ERROR",
                    "SECTION020",
                    f"Requirement {requirement_id} source range has no section coverage: {value}",
                    path.relative_to(root).as_posix(),
                )
