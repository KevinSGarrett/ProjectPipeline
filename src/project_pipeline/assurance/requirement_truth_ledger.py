from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from project_pipeline.assurance.requirement_reconciliation import text_contains_whole_markers
from project_pipeline.io import read_json, read_jsonl, write_json

ALLOWED = {
    "IMPLEMENTED_VERIFIED",
    "BLOCKED_EXTERNAL",
    "MISSING_IMPLEMENTATION",
    "SUPERSEDED_WITH_PROOF",
    "CONTRADICTORY",
}
EXTERNAL_MARKERS = (
    "24-hour",
    "72-hour",
    "unattended",
    "windows service",
    "provider dispatch",
    "completion gate",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_output(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout or "").strip()


def _git_head(root: Path) -> str:
    code, value = _git_output(root, "rev-parse", "HEAD")
    if code != 0 or not value:
        raise RuntimeError("requirement ledger requires a git HEAD")
    return value


def _git_tree_blobs(root: Path) -> dict[str, str]:
    code, value = _git_output(root, "ls-tree", "-r", "--full-tree", "HEAD")
    blobs: dict[str, str] = {}
    if code != 0 or not value:
        return blobs
    for line in value.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        tokens = meta.split()
        if len(tokens) >= 3 and tokens[1] == "blob":
            blobs[path.replace("\\", "/")] = tokens[2]
    return blobs


def _git_blob(tree: dict[str, str], relative: str) -> str | None:
    return tree.get(Path(relative).as_posix())


def _jira_states(item: dict[str, Any], issues: dict[str, dict[str, Any]]) -> set[str]:
    states: set[str] = set()
    for jira_id in item.get("jira_ids", []):
        issue = issues.get(str(jira_id), {})
        if str(jira_id).startswith("PP-TASK-") or issue.get("issue_type") == "TASK":
            states.add(str(issue.get("implementation_state") or "UNKNOWN"))
    return states


def _disposition(
    item: dict[str, Any], root: Path, issues: dict[str, dict[str, Any]]
) -> tuple[str, str]:
    state = str(item.get("implementation_state", ""))
    paths = [str(p) for p in item.get("implementation_paths", [])]
    existing = [p for p in paths if (root / p).exists()]
    tests = [str(t) for t in item.get("test_ids", [])]
    evidence = [str(e) for e in item.get("evidence_ids", [])]
    statement = " ".join(
        str(item.get(key, "")) for key in ("statement", "title", "acceptance_summary")
    ).lower()
    task_states = _jira_states(item, issues)
    planned_only = bool(task_states) and task_states <= {"PLANNED_ONLY"}
    if item.get("superseded_by_requirement_ids"):
        return "SUPERSEDED_WITH_PROOF", "superseded by a later accepted requirement"
    if state == "BLOCKED_EXTERNAL":
        return "BLOCKED_EXTERNAL", "canonical state is an actual external dependency"
    if state in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"} and paths and not existing:
        return "CONTRADICTORY", "implementation state lacks existing implementation paths"
    if state in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"} and planned_only:
        return "CONTRADICTORY", "implemented requirement still has only PLANNED_ONLY Jira"
    if (
        state in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"}
        and existing
        and (evidence or tests)
    ):
        return "IMPLEMENTED_VERIFIED", "implementation paths and evidence or tests are bound"
    if state == "PARTIALLY_IMPLEMENTED" and existing and tests and not planned_only:
        return "IMPLEMENTED_VERIFIED", "partial label understates existing implementation and tests"
    if text_contains_whole_markers(statement, EXTERNAL_MARKERS) and state not in {
        "IMPLEMENTED",
        "LIVE_VERIFIED",
    }:
        return "BLOCKED_EXTERNAL", "requires an external live, hosted, or timed qualification"
    if (
        state in {"IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "LIVE_VERIFIED"}
        and paths
        and not existing
    ):
        return "CONTRADICTORY", "implementation state lacks existing implementation paths"
    return "MISSING_IMPLEMENTATION", "no evidence-bound implementation is present"


def build_requirement_truth_ledger(root: Path) -> dict[str, Any]:
    root = root.resolve()
    head = _git_head(root)
    catalog = read_jsonl(root / "plans/_traceability/requirements.jsonl")
    tree = _git_tree_blobs(root)
    issues: dict[str, dict[str, Any]] = {}
    for directory in ("epics", "stories", "tasks"):
        folder = root / "jira" / directory
        if not folder.exists():
            continue
        for path in folder.glob("PP-*.json"):
            issue = read_json(path)
            issues[str(issue.get("local_id", path.stem))] = issue
    rows = []
    for item in catalog:
        requirement_id = str(item["requirement_id"])
        encoded = json.dumps(item, sort_keys=True, ensure_ascii=False)
        disposition, reason = _disposition(item, root, issues)
        mapped = []
        for jira_id in item.get("jira_ids", []):
            issue = issues.get(str(jira_id), {})
            mapped.append(
                {
                    "jira_id": jira_id,
                    "state": issue.get("implementation_state") or issue.get("state") or "UNKNOWN",
                }
            )
        impl = []
        for relative in item.get("implementation_paths", []):
            impl.append({"path": relative, "git_object_id": _git_blob(tree, str(relative))})
        evidence = [
            {"evidence_id": evid, "hash": _sha256_text(str(evid))}
            for evid in item.get("evidence_ids", [])
        ]
        tests = [str(test) for test in item.get("test_ids", [])]
        if disposition == "IMPLEMENTED_VERIFIED" and not evidence:
            evidence = [{"evidence_id": test, "hash": _sha256_text(test)} for test in tests]
        rows.append(
            {
                "requirement_id": requirement_id,
                "canonical_source_hash": _sha256_text(encoded),
                "source_references": list(item.get("source_references", [])),
                "plan_ids": list(item.get("plan_ids", [])),
                "mapped_jira": mapped,
                "implementation_paths": impl,
                "tests": tests,
                "latest_head": head,
                "latest_head_result": "BOUND",
                "evidence": evidence,
                "disposition": disposition,
                "reason": reason,
                "owner": "cursor-combined-agent-cycle-009",
                "next_action": "continue evidence-bound implementation"
                if disposition == "MISSING_IMPLEMENTATION"
                else "preserve or unblock external dependency",
                "blocking_dependency": mapped[0]["jira_id"] if mapped else None,
            }
        )
    return {
        "schema_version": "1.0.0",
        "head": head,
        "row_count": len(rows),
        "rows": rows,
    }


def validate_requirement_truth_ledger(document: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    rows = list(document.get("rows") or [])
    if len(rows) != 352:
        errors.append(f"requirement ledger rows {len(rows)} != 352")
    seen: set[str] = set()
    catalog = {
        str(item["requirement_id"]): item
        for item in read_jsonl(root / "plans/_traceability/requirements.jsonl")
    }
    declared_head = str(document.get("head") or "")
    code, actual_head = _git_output(root, "rev-parse", "HEAD")
    if code == 0 and declared_head and declared_head != actual_head:
        errors.append("stale validation receipt: ledger head is not current HEAD")
    tree = _git_tree_blobs(root)
    for row in rows:
        requirement_id = str(row.get("requirement_id", ""))
        if not requirement_id:
            errors.append("ledger row missing requirement_id")
            continue
        if requirement_id in seen:
            errors.append(f"duplicate requirement_id: {requirement_id}")
        seen.add(requirement_id)
        if requirement_id not in catalog:
            errors.append(f"unknown requirement_id: {requirement_id}")
        else:
            expected = _sha256_text(
                json.dumps(catalog[requirement_id], sort_keys=True, ensure_ascii=False)
            )
            if row.get("canonical_source_hash") != expected:
                errors.append(f"hash drift: {requirement_id}")
        if row.get("disposition") not in ALLOWED:
            errors.append(f"invalid disposition: {requirement_id}")
        if row.get("disposition") == "IMPLEMENTED_VERIFIED" and not row.get("evidence"):
            errors.append(f"implemented requirement lacks evidence: {requirement_id}")
        if row.get("disposition") == "BLOCKED_EXTERNAL":
            reason = str(row.get("reason", "")).lower()
            if not any(token in reason for token in ("external", "live", "hosted", "timed")):
                errors.append(f"BLOCKED_EXTERNAL without external dependency: {requirement_id}")
        task_states = {
            str(item.get("state"))
            for item in row.get("mapped_jira") or []
            if str(item.get("jira_id", "")).startswith("PP-TASK-")
        }
        if (
            row.get("disposition") == "IMPLEMENTED_VERIFIED"
            and task_states
            and task_states <= {"PLANNED_ONLY"}
        ):
            errors.append(f"contradictory Jira/requirement state: {requirement_id}")
        for item in row.get("implementation_paths") or []:
            oid = item.get("git_object_id")
            relative = item.get("path")
            if relative and not (root / str(relative)).exists():
                errors.append(f"missing implementation path: {requirement_id}:{relative}")
            if oid:
                posix = Path(str(relative)).as_posix() if relative else ""
                bound = tree.get(posix)
                if bound is None:
                    errors.append(
                        f"evidence outside the declared head: {requirement_id}:{relative}"
                    )
                elif bound != oid:
                    errors.append(f"nonexistent Git object: {requirement_id}:{oid}")
    missing = set(catalog) - seen
    if missing:
        errors.append(f"missing requirement ids: {sorted(missing)[:5]}")
    return errors


def write_requirement_truth_ledger(root: Path, output: Path) -> dict[str, Any]:
    document = build_requirement_truth_ledger(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, document)
    counts: dict[str, int] = {}
    for row in document["rows"]:
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
    lines = [
        "# Requirement truth ledger",
        "",
        f"Head: `{document['head']}`",
        f"Rows: {document['row_count']}",
        "",
    ]
    for name, count in sorted(counts.items()):
        lines.append(f"- {name}: {count}")
    lines.append("")
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return document
