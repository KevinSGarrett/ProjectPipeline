"""Machine-readable continuation packages that do not depend on chat history."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.github_steward.local_git import LocalGitRepository
from project_pipeline.io import read_jsonl, sha256_canonical_file
from project_pipeline.release_hardening.candidate import resolve_candidate_identity

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_HUMAN_MARKERS = (
    "HUMAN" + "_REQUIRED",
    "PM review proposed",
    "nothing else to implement",
)


def _session_handoff_fields(root: Path) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    project_manifest = root / "PROJECT_MANIFEST.json"
    file_manifest = root / "FILE_MANIFEST.sha256"
    test_catalog = root / "tests" / "TEST_CATALOG.json"
    coverage_path = root / "plans/_traceability/coverage_report.json"
    if project_manifest.is_file():
        artifacts["project_manifest_sha256"] = sha256_canonical_file(project_manifest)
    if file_manifest.is_file():
        artifacts["file_manifest_sha256"] = sha256_canonical_file(file_manifest)
    tests: dict[str, Any] = {"available": test_catalog.is_file(), "test_catalog_count": 0}
    if test_catalog.is_file():
        catalog = json.loads(test_catalog.read_text(encoding="utf-8"))
        tests["test_catalog_count"] = int(catalog.get("test_count") or 0)
    coverage: dict[str, Any] = {"available": coverage_path.is_file()}
    if coverage_path.is_file():
        report = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage["unexplained_gap_count"] = int(
            report.get("unexplained_gap_count", report.get("gap_count", 0))
        )
    decisions: list[str] = []
    adr_catalog = root / "adr" / "ADR_CATALOG.json"
    if adr_catalog.is_file():
        payload = json.loads(adr_catalog.read_text(encoding="utf-8"))
        items = payload.get("adrs") or payload.get("decisions") or []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or item.get("state") or "").upper()
                if status in {"OPEN", "PROPOSED", "DRAFT"}:
                    decisions.append(str(item.get("decision_id") or item.get("adr_id") or ""))
        decisions = [item for item in decisions if item]
    blockers: list[str] = []
    try:
        from project_pipeline.assurance import build_repository_gate_facts, evaluate_completion_gate

        gate = evaluate_completion_gate(build_repository_gate_facts(root, "PROJECT-PIPELINE"))
        blockers = [
            reason
            for question in gate.questions
            if not question.passed
            for reason in question.reasons
        ]
        if not blockers:
            blockers = [item.detail for item in gate.failures]
        completion_state = gate.state.value
    except Exception:
        completion_state = "UNAVAILABLE"
        blockers = ["completion projection is unavailable in this workspace"]
    return {
        "artifacts": artifacts,
        "tests": tests,
        "coverage": coverage,
        "decisions": decisions,
        "blockers": blockers,
        "completion_state": completion_state,
    }


def _has_control_characters(value: Any) -> bool:
    if isinstance(value, str):
        return _CONTROL_CHARS.search(value) is not None
    if isinstance(value, dict):
        return any(_has_control_characters(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_control_characters(item) for item in value)
    return False


def build_continuation_package(root: Path) -> dict[str, Any]:
    """Record current repository identity, completion reasons, and next autonomous work."""

    root = root.resolve()
    source_sha, source_tree = resolve_candidate_identity(root)
    local = LocalGitRepository(root)
    branch = local.current_branch_name()
    staged, unstaged, untracked = local.status_paths()
    requirements = read_jsonl(root / "plans/_traceability/requirements.jsonl")
    complete = {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED", "BLOCKED_EXTERNAL"}
    incomplete = [
        item
        for item in requirements
        if item.get("disposition") == "ACCEPTED"
        and item.get("implementation_state") not in complete
    ]
    package = {
        "schema_version": "1.1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "project_id": "PROJECT-PIPELINE",
        "source_sha": source_sha,
        "source_tree": source_tree,
        "branch": branch,
        "dirty": bool(staged or unstaged or untracked),
        "requirement_count": len(requirements),
        "incomplete_requirement_count": len(incomplete),
        "incomplete_requirement_ids": [str(item.get("requirement_id")) for item in incomplete],
        **_session_handoff_fields(root),
        "next_autonomous_work": (
            "implement the highest-impact remaining incomplete Completion Gate domain, "
            "then reconcile evidence-backed Jira and requirement truth"
        ),
        "user_action_required": False,
        "depends_on_chat_history": False,
        "final_release_candidate": False,
    }
    errors = validate_continuation_package(package)
    if errors:
        raise ValueError("; ".join(errors))
    return package


def validate_continuation_package(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    serialized = json.dumps(package, ensure_ascii=False, sort_keys=True)
    if _has_control_characters(package) or _CONTROL_CHARS.search(serialized):
        errors.append("continuation package contains ASCII control characters")
    sha = str(package.get("source_sha") or "")
    tree = str(package.get("source_tree") or "")
    if not _FULL_SHA.fullmatch(sha):
        errors.append("continuation package source_sha must be a full 40-hex Git identity")
    if not _FULL_SHA.fullmatch(tree):
        errors.append("continuation package source_tree must be a full 40-hex Git identity")
    if package.get("user_action_required") is not False:
        errors.append("continuation package must not require a user action")
    if package.get("depends_on_chat_history") is not False:
        errors.append("continuation package must not depend on chat history")
    for key in ("artifacts", "tests", "coverage", "decisions", "blockers", "next_autonomous_work"):
        if key not in package:
            errors.append(f"continuation package missing session handoff field: {key}")
    blob = serialized.casefold()
    for marker in _HUMAN_MARKERS:
        if marker.casefold() in blob:
            errors.append(f"continuation package contains forbidden marker: {marker}")
    return errors
