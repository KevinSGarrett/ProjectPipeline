"""Refresh repository and workspace state after an integrated merge."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.github_steward.local_git import LocalGitError, LocalGitRepository
from project_pipeline.release_hardening.candidate import resolve_candidate_identity

_PINNED_NAME_MARKERS = (
    "cycle-012-pp385-qualify",
    "cycle-011-autonomous-recovery",
)
_PROTECTED_BRANCHES = frozenset({"main", "master", "HEAD"})


def _rev_parse(root: Path, argument: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", argument],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    value = (completed.stdout or "").strip().lower()
    if completed.returncode != 0 or len(value) != 40:
        return None
    return value


def _is_pinned(path: Path, extra_pinned: tuple[str, ...]) -> bool:
    text = str(path).replace("\\", "/").casefold()
    markers = (*_PINNED_NAME_MARKERS, *extra_pinned)
    return any(marker.casefold() in text for marker in markers if marker.strip())


def _integrated_verification(root: Path) -> dict[str, Any]:
    required = (
        root / "PROJECT_MANIFEST.json",
        root / "FILE_MANIFEST.sha256",
        root / "plans/_traceability/coverage_report.json",
        root / "evidence/EVIDENCE_SUMMARY.json",
    )
    if not all(path.is_file() for path in required):
        return {
            "available": False,
            "final_passed": False,
            "reason": "integrated verification inputs are not present in this workspace",
        }
    from project_pipeline.verification.post_merge import evaluate_post_merge

    report = evaluate_post_merge(root, required_test_suite_ok=True)
    return {
        "available": True,
        "final_passed": report.final_passed,
        "report_id": report.report_id,
        "observations": list(report.observations),
    }


def plan_post_merge_refresh(
    root: Path,
    *,
    expected_sha: str | None = None,
    expected_tree: str | None = None,
    pinned_worktrees: tuple[str, ...] = (),
    apply: bool = False,
) -> dict[str, Any]:
    """Classify workspaces and verify the integrated result. Removal requires apply."""

    root = root.resolve()
    local = LocalGitRepository(root)
    source_sha, source_tree = resolve_candidate_identity(root)
    origin_sha = _rev_parse(root, "origin/main") or _rev_parse(root, "main")
    origin_tree = _rev_parse(root, "origin/main^{tree}") or _rev_parse(root, "main^{tree}")
    identity_errors: list[str] = []
    if expected_sha and expected_sha.lower() != (origin_sha or ""):
        identity_errors.append("origin/main SHA does not match the expected integrated identity")
    if expected_tree and expected_tree.lower() != (origin_tree or ""):
        identity_errors.append("origin/main tree does not match the expected integrated identity")
    workspaces: list[dict[str, Any]] = []
    closed: list[str] = []
    for item in local.worktrees():
        path = Path(item.path).resolve(strict=False)
        disposition = "CLOSE_ELIGIBLE"
        reasons: list[str] = []
        if path == root:
            disposition = "PRESERVE"
            reasons.append("current repository root")
        if _is_pinned(path, pinned_worktrees):
            disposition = "PRESERVE"
            reasons.append("pinned campaign or recovery worktree")
        if item.state.value in {"DIRTY", "MISSING"}:
            disposition = "PRESERVE"
            reasons.append(f"worktree state is {item.state.value}")
        if item.state.value == "DETACHED":
            disposition = "PRESERVE"
            reasons.append("detached worktree is preserved until ownership analysis")
        branch = item.branch or ""
        if branch in _PROTECTED_BRANCHES:
            disposition = "PRESERVE"
            reasons.append("protected default branch worktree")
        if disposition == "CLOSE_ELIGIBLE" and not reasons:
            reasons.append("clean feature worktree is eligible for post-merge close")
        record = {
            "path": str(path),
            "branch": branch or None,
            "head_sha": item.head_sha,
            "state": item.state.value,
            "disposition": disposition,
            "reasons": reasons,
            "closed": False,
        }
        if apply and disposition == "CLOSE_ELIGIBLE":
            try:
                local.remove_worktree(path, apply=True)
                record["closed"] = True
                closed.append(str(path))
            except LocalGitError as exc:
                record["disposition"] = "PRESERVE"
                record["closed"] = False
                reasons.append(str(exc))
        workspaces.append(record)
    payload = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(root),
        "source_sha": source_sha,
        "source_tree": source_tree,
        "origin_main_sha": origin_sha,
        "origin_main_tree": origin_tree,
        "identity_errors": identity_errors,
        "applied": apply,
        "workspaces": workspaces,
        "closed_worktrees": closed,
        "integrated_verification": _integrated_verification(root),
        "jira_refresh": {
            "planned": True,
            "applied": False,
            "reason": "live Jira refresh remains a separate steward snapshot/apply",
        },
        "user_action_required": False,
    }
    if identity_errors:
        payload["ok"] = False
    else:
        payload["ok"] = not apply or all(
            item["disposition"] == "PRESERVE" or item["closed"] for item in workspaces
        )
    return payload


def dumps_status(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
