from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from project_pipeline.domain.evidence_observation import (
    MetadataOnlyDiffProof,
    canonical_fingerprint,
)
from project_pipeline.io import read_jsonl, sha256_canonical_file

METADATA_PATH_PREFIXES = (
    "jira/",
    "docs/generated/",
    "evidence/generated/",
    "plans/_traceability/requirements_by_id.json",
    "plans/_traceability/coverage_report.json",
)
METADATA_EXACT_PATHS = {
    "plans/_traceability/requirements.jsonl",
    "jira/BOARD_MANIFEST.json",
    "jira/indexes/issues.jsonl",
    "jira/indexes/issues_by_id.json",
    "jira/relationships/graph.json",
}
METADATA_REQUIREMENT_FIELDS = {"implementation_state"}


def normalize_repo_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def acceptance_scope_fingerprint(
    root: Path,
    item: dict[str, Any],
    *,
    evidence_ids: Iterable[str] | None = None,
) -> str:
    """Hash acceptance-bearing source, not derived implementation-state labels."""

    root = root.resolve()
    paths = [normalize_repo_path(str(path)) for path in item.get("implementation_paths", [])]
    test_ids = [str(test_id) for test_id in item.get("test_ids", [])]
    evidence = [str(evidence_id) for evidence_id in (evidence_ids or item.get("evidence_ids", []))]
    payload: dict[str, Any] = {
        "requirement_id": item.get("requirement_id"),
        "statement": item.get("statement"),
        "title": item.get("title"),
        "acceptance_summary": item.get("acceptance_summary"),
        "test_ids": test_ids,
        "evidence_ids": evidence,
        "implementation_paths": {},
    }
    for relative in paths:
        path = root / relative
        if path.is_file():
            payload["implementation_paths"][relative] = sha256_canonical_file(path)
        elif path.is_dir():
            files = {
                child.relative_to(path).as_posix(): sha256_canonical_file(child)
                for child in sorted(path.rglob("*"))
                if child.is_file()
            }
            payload["implementation_paths"][relative] = files
        else:
            payload["implementation_paths"][relative] = None
    return canonical_fingerprint(payload)


def is_metadata_only_path(relative: str) -> bool:
    value = normalize_repo_path(relative)
    if value in METADATA_EXACT_PATHS:
        return True
    return any(value.startswith(prefix) for prefix in METADATA_PATH_PREFIXES)


def requirements_jsonl_is_metadata_only(root: Path, from_sha: str, to_sha: str) -> bool:
    before = _show_jsonl(root, from_sha, "plans/_traceability/requirements.jsonl")
    after = _show_jsonl(root, to_sha, "plans/_traceability/requirements.jsonl")
    if before is None or after is None:
        return False
    if len(before) != len(after):
        return False
    for left, right in zip(before, after, strict=True):
        left_copy = dict(left)
        right_copy = dict(right)
        for field in METADATA_REQUIREMENT_FIELDS:
            left_copy.pop(field, None)
            right_copy.pop(field, None)
        if left_copy != right_copy:
            return False
    return True


def prove_metadata_only_diff(
    root: Path,
    *,
    from_sha: str,
    to_sha: str,
    from_tree: str,
    to_tree: str,
    acceptance_scope_unchanged: bool,
) -> MetadataOnlyDiffProof:
    changed = _diff_names(root, from_sha, to_sha)
    allowlisted = bool(changed) and all(is_metadata_only_path(path) for path in changed)
    if allowlisted and any(
        normalize_repo_path(path) == "plans/_traceability/requirements.jsonl" for path in changed
    ):
        allowlisted = requirements_jsonl_is_metadata_only(root, from_sha, to_sha)
    reason = (
        "allowlisted metadata-only diff" if allowlisted else "acceptance-bearing or unknown diff"
    )
    if not changed:
        reason = "empty diff"
        allowlisted = True
    return MetadataOnlyDiffProof(
        from_sha=from_sha,
        to_sha=to_sha,
        from_tree=from_tree,
        to_tree=to_tree,
        changed_paths=tuple(changed),
        allowlisted=allowlisted,
        acceptance_scope_unchanged=acceptance_scope_unchanged,
        reason=reason,
    )


def _diff_names(root: Path, from_sha: str, to_sha: str) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", from_sha, to_sha],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        return ["<unreadable-diff>"]
    return [normalize_repo_path(line) for line in completed.stdout.splitlines() if line.strip()]


def _show_jsonl(root: Path, sha: str, relative: str) -> list[dict[str, Any]] | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "show", f"{sha}:{relative}"],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        path = root / relative
        if not path.is_file():
            return None
        return list(read_jsonl(path))
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
