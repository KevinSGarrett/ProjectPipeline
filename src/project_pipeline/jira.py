from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, write_json, write_jsonl

ISSUE_DIRECTORIES = ("epics", "stories", "tasks", "subtasks", "bugs", "spikes")
ISSUE_TYPES = ("BUG", "EPIC", "SPIKE", "STORY", "SUBTASK", "TASK")


def _issue_sort_key(issue: dict[str, Any]) -> tuple[int, str]:
    local_id = str(issue["local_id"])
    return int(local_id.rsplit("-", 1)[1]), local_id


def load_issues(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for directory in ISSUE_DIRECTORIES:
        folder = root / "jira" / directory
        if not folder.exists():
            continue
        for path in sorted(folder.glob("PP-*.json")):
            rows.append(read_json(path))
    return sorted(rows, key=_issue_sort_key)


def _deduplicate_edges(edges: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, str]] = []
    for edge in edges:
        key = (edge["from"], edge["to"], edge["type"])
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return sorted(result, key=lambda edge: (edge["from"], edge["to"], edge["type"]))


def build_relationship_edges(issues: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Build the canonical, deduplicated Jira relationship graph."""
    edges: list[dict[str, str]] = []
    for issue in issues:
        issue_id = issue["local_id"]
        for relationship in issue.get("relationships", []):
            edges.append(
                {
                    "from": issue_id,
                    "to": relationship["target"],
                    "type": relationship["type"],
                }
            )
        for dependency in issue.get("dependencies", []):
            edges.append({"from": issue_id, "to": dependency, "type": "DEPENDS_ON"})
        parent = issue.get("parent")
        if parent:
            edges.extend(
                [
                    {"from": parent, "to": issue_id, "type": "PARENT_OF"},
                    {"from": issue_id, "to": parent, "type": "CHILD_OF"},
                ]
            )
    return _deduplicate_edges(edges)


def rebuild_jira_indexes(root: Path) -> dict[str, Any]:
    issues = load_issues(root)
    by_id = {item["local_id"]: item for item in issues}
    edges = build_relationship_edges(issues)
    indexes = root / "jira" / "indexes"
    relationships = root / "jira" / "relationships"
    write_jsonl(indexes / "issues.jsonl", issues)
    write_json(indexes / "issues_by_id.json", by_id)
    write_jsonl(relationships / "issues.jsonl", edges)
    graph = {
        "schema_version": "1.0.0",
        "node_count": len(issues),
        "edge_count": len(edges),
        "nodes": [
            {
                "id": item["local_id"],
                "type": item["issue_type"],
                "state": item["state"],
                "title": item["title"],
            }
            for item in issues
        ],
        "edges": edges,
    }
    write_json(relationships / "graph.json", graph)
    by_type = Counter(item["issue_type"] for item in issues)
    by_state = Counter(item["state"] for item in issues)
    manifest = {
        "schema_version": "1.0.0",
        "board_id": "PROJECT-PIPELINE-LOCAL",
        "project_key": "PP",
        "remote_board_state": "NOT_CONNECTED",
        "remote_write_state": "DENIED_BY_DEFAULT",
        "issue_count": len(issues),
        "counts_by_type": {kind: by_type.get(kind, 0) for kind in ISSUE_TYPES},
        "counts_by_state": dict(sorted(by_state.items())),
        "issue_index": "jira/indexes/issues.jsonl",
        "relationship_graph": "jira/relationships/graph.json",
        "source_context_directory": "jira/source_context",
        "last_generated_date": "2026-08-14",
    }
    write_json(root / "jira" / "BOARD_MANIFEST.json", manifest)
    status = {
        "schema_version": "1.0.0",
        "issue_count": len(issues),
        "counts_by_type": {kind: by_type.get(kind, 0) for kind in ISSUE_TYPES},
        "counts_by_state": dict(sorted(by_state.items())),
        "requirements_referenced": len(
            {
                requirement_id
                for item in issues
                for requirement_id in item.get("requirement_ids", [])
            }
        ),
        "edge_count": len(edges),
    }
    write_json(root / "jira" / "reports" / "backlog_status.json", status)
    return {"manifest": manifest, "graph": graph, "status": status}
