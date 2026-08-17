from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_pipeline.domain.jira import (
    JiraIssueType,
    JiraMirrorBundle,
    JiraRelationshipType,
    LocalJiraIssue,
)
from project_pipeline.io import read_json, read_jsonl, write_json
from project_pipeline.jira import ISSUE_DIRECTORIES, build_relationship_edges


class JiraMirrorValidationError(ValueError):
    """Raised when the source-controlled Jira mirror violates semantic invariants."""


@dataclass(frozen=True, slots=True)
class JiraMirrorValidationReport:
    issue_count: int
    edge_count: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "issue_count": self.issue_count,
            "edge_count": self.edge_count,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class JiraMirrorRepository:
    """Typed read-only access to the source-controlled Jira mirror."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load_issues(self) -> tuple[LocalJiraIssue, ...]:
        issues: list[LocalJiraIssue] = []
        for directory in ISSUE_DIRECTORIES:
            folder = self.root / "jira" / directory
            if not folder.exists():
                continue
            for path in sorted(folder.glob("PP-*.json")):
                issues.append(LocalJiraIssue.model_validate(read_json(path)))
        return tuple(sorted(issues, key=lambda item: item.local_id))

    def by_id(self) -> dict[str, LocalJiraIssue]:
        return {item.local_id: item for item in self.load_issues()}

    def bundle(self) -> JiraMirrorBundle:
        issues = self.load_issues()
        board = read_json(self.root / "jira" / "BOARD_MANIFEST.json")
        graph = read_json(self.root / "jira" / "relationships" / "graph.json")
        payload = [item.model_dump(mode="json") for item in issues]
        import hashlib

        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        fingerprint = hashlib.sha256(encoded).hexdigest()
        return JiraMirrorBundle(
            board_id=str(board["board_id"]),
            project_key=str(board["project_key"]),
            issues=issues,
            issue_count=len(issues),
            edge_count=int(graph["edge_count"]),
            fingerprint=fingerprint,
        )

    def validate(self) -> JiraMirrorValidationReport:
        return validate_jira_mirror(self.root, self.load_issues())


def _cycle_nodes(edges: dict[str, set[str]]) -> tuple[str, ...]:
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: set[str] = set()

    def walk(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            cycle.add(node)
            return
        visiting.add(node)
        for dependency in edges.get(node, set()):
            if dependency in visiting:
                cycle.update({node, dependency})
            else:
                walk(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        walk(node)
    return tuple(sorted(cycle))


def validate_jira_mirror(
    root: Path,
    issues: tuple[LocalJiraIssue, ...] | None = None,
) -> JiraMirrorValidationReport:
    repository = JiraMirrorRepository(root)
    issues = repository.load_issues() if issues is None else issues
    by_id = {item.local_id: item for item in issues}
    errors: list[str] = []
    warnings: list[str] = []
    child_counts: Counter[str] = Counter()
    parent_edges: dict[str, set[str]] = defaultdict(set)
    dependency_edges: dict[str, set[str]] = defaultdict(set)
    remote_keys: dict[str, str] = {}
    edge_count = 0
    allowed_parents = {
        JiraIssueType.STORY: {JiraIssueType.EPIC},
        JiraIssueType.TASK: {JiraIssueType.STORY, JiraIssueType.EPIC},
        JiraIssueType.SUBTASK: {JiraIssueType.TASK},
        JiraIssueType.BUG: {JiraIssueType.STORY, JiraIssueType.EPIC},
        JiraIssueType.SPIKE: {JiraIssueType.STORY, JiraIssueType.EPIC},
    }
    for issue in issues:
        if issue.remote_jira_key:
            previous = remote_keys.get(issue.remote_jira_key)
            if previous is not None:
                errors.append(
                    f"remote Jira key {issue.remote_jira_key} maps to both {previous} and {issue.local_id}"
                )
            remote_keys[issue.remote_jira_key] = issue.local_id
        if issue.parent is not None:
            parent = by_id.get(issue.parent)
            if parent is None:
                errors.append(f"{issue.local_id} has missing parent {issue.parent}")
            else:
                child_counts[parent.local_id] += 1
                parent_edges[issue.local_id].add(parent.local_id)
                if parent.issue_type not in allowed_parents.get(issue.issue_type, set()):
                    errors.append(
                        f"{issue.local_id} has invalid {parent.issue_type.value} parent {parent.local_id}"
                    )
        for dependency in issue.dependencies:
            if dependency not in by_id:
                errors.append(f"{issue.local_id} depends on missing issue {dependency}")
            else:
                dependency_edges[issue.local_id].add(dependency)
        for blocker in issue.blockers:
            if blocker not in by_id:
                errors.append(f"{issue.local_id} is blocked by missing issue {blocker}")
        for relationship in issue.relationships:
            edge_count += 1
            target = by_id.get(relationship.target)
            if target is None:
                errors.append(
                    f"{issue.local_id} has dangling {relationship.type.value} relationship to {relationship.target}"
                )
                continue
            if (
                relationship.type is JiraRelationshipType.CHILD_OF
                and issue.parent != target.local_id
            ):
                errors.append(
                    f"{issue.local_id} CHILD_OF {target.local_id} disagrees with parent {issue.parent}"
                )
            if (
                relationship.type is JiraRelationshipType.PARENT_OF
                and target.parent != issue.local_id
            ):
                errors.append(
                    f"{issue.local_id} PARENT_OF {target.local_id} disagrees with target parent {target.parent}"
                )
            if (
                relationship.type is JiraRelationshipType.DEPENDS_ON
                and target.local_id not in issue.dependencies
            ):
                errors.append(
                    f"{issue.local_id} DEPENDS_ON {target.local_id} is absent from dependencies"
                )
        planned_dependency_relationships = {
            item.target
            for item in issue.relationships
            if item.type is JiraRelationshipType.DEPENDS_ON
        }
        if planned_dependency_relationships and not planned_dependency_relationships.issubset(
            set(issue.dependencies)
        ):
            errors.append(f"{issue.local_id} relationship dependencies are internally inconsistent")
    for issue in issues:
        if issue.issue_type is JiraIssueType.EPIC and child_counts[issue.local_id] == 0:
            errors.append(f"epic {issue.local_id} is orphaned")
    parent_cycles = _cycle_nodes(parent_edges)
    if parent_cycles:
        errors.append(f"Jira hierarchy contains a cycle involving {', '.join(parent_cycles)}")
    dependency_cycles = _cycle_nodes(dependency_edges)
    if dependency_cycles:
        errors.append(
            f"Jira dependency graph contains a cycle involving {', '.join(dependency_cycles)}"
        )
    graph_path = root / "jira" / "relationships" / "graph.json"
    if graph_path.exists():
        graph = read_json(graph_path)
        if int(graph.get("node_count", -1)) != len(issues):
            errors.append("stored Jira graph node_count is stale")
        generated_edges = graph.get("edges", [])
        if int(graph.get("edge_count", -1)) != len(generated_edges):
            errors.append("stored Jira graph edge_count is stale")
        expected_edges = build_relationship_edges(item.model_dump(mode="json") for item in issues)
        if generated_edges != expected_edges:
            errors.append("stored Jira graph edges differ from canonical issue relationships")
        graph_ids = {node.get("id") for node in graph.get("nodes", [])}
        if graph_ids != set(by_id):
            errors.append("stored Jira graph nodes differ from typed issue records")
    else:
        errors.append("stored Jira relationship graph is missing")
    issue_index_path = root / "jira" / "indexes" / "issues.jsonl"
    issue_by_id_path = root / "jira" / "indexes" / "issues_by_id.json"
    expected_issue_rows = {item.local_id: item.model_dump(mode="json") for item in issues}
    observed_issue_rows = (
        {str(item.get("local_id")): item for item in read_jsonl(issue_index_path)}
        if issue_index_path.exists()
        else {}
    )
    if observed_issue_rows != expected_issue_rows:
        errors.append("stored Jira issue index differs from canonical source issues")
    if not issue_by_id_path.exists() or read_json(issue_by_id_path) != expected_issue_rows:
        errors.append("stored Jira issue-by-id index differs from canonical source issues")
    if any(item.last_observed_remote_state for item in issues) and not remote_keys:
        warnings.append("remote observations exist without stable remote Jira key mappings")
    return JiraMirrorValidationReport(
        issue_count=len(issues),
        edge_count=edge_count,
        errors=tuple(sorted(set(errors))),
        warnings=tuple(sorted(set(warnings))),
    )


def export_jira_mirror(root: Path, output: Path) -> JiraMirrorBundle:
    repository = JiraMirrorRepository(root)
    report = repository.validate()
    if not report.valid:
        raise JiraMirrorValidationError("; ".join(report.errors))
    bundle = repository.bundle()
    write_json(output, bundle.model_dump(mode="json"))
    return bundle


def load_jira_export(path: Path) -> JiraMirrorBundle:
    return JiraMirrorBundle.model_validate(read_json(path))
