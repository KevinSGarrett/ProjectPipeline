"""Detect and preserve recoverable uncommitted work before cleanup or failover."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.github_steward.local_git import LocalGitError, LocalGitRepository
from project_pipeline.io import sha256_file
from project_pipeline.resilience.restore import (
    RestoreTargetPolicy,
    _is_protected,
    has_traversal,
    is_drive_or_share_root,
    is_unc,
)

_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template"})


def _is_secret_path(relative: str) -> bool:
    name = Path(relative).name
    if name == ".env" or (name.startswith(".env.") and name not in _ENV_TEMPLATES):
        return True
    return name.endswith(".pem") or name.endswith(".key")


class WipPreserveError(RuntimeError):
    """Fail-closed uncommitted-work preservation error."""


def _safe_destination(destination: Path, root: Path | None = None) -> Path:
    raw = str(destination)
    if has_traversal(raw) or is_unc(raw) or is_drive_or_share_root(raw):
        raise WipPreserveError("WIP destination is a filesystem root, UNC path, or traversal")
    candidate = destination.expanduser().resolve(strict=False)
    if is_drive_or_share_root(candidate) or is_unc(candidate):
        raise WipPreserveError("WIP destination is a filesystem root, UNC path, or traversal")
    if _is_protected(candidate):
        raise WipPreserveError("WIP destination cannot be a protected or system path")
    if any(part.casefold() == ".git" for part in candidate.parts):
        raise WipPreserveError("WIP destination cannot be inside .git")
    if root is None:
        return candidate
    resolved_root = root.resolve()
    if candidate == resolved_root:
        raise WipPreserveError("WIP destination cannot be the repository root")
    git_dir = (resolved_root / ".git").resolve()
    if candidate == git_dir or git_dir in candidate.parents:
        raise WipPreserveError("WIP destination cannot be inside .git")
    return candidate


def preserve_uncommitted_work(
    root: Path,
    destination: Path,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Copy recoverable dirty/untracked files and metadata. Never deletes the source."""

    root = root.resolve()
    dest = _safe_destination(destination, root)
    try:
        local = LocalGitRepository(root)
        snapshot = local.snapshot()
        staged, unstaged, untracked = local.status_paths()
    except LocalGitError as exc:
        raise WipPreserveError(str(exc)) from exc
    recoverable = []
    skipped_secrets = []
    for relative in (*staged, *unstaged, *untracked):
        posix = relative.replace("\\", "/")
        if _is_secret_path(posix):
            skipped_secrets.append(posix)
            continue
        source = root / relative
        if not source.is_file():
            continue
        recoverable.append(posix)
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(root),
        "destination": str(dest),
        "head_sha": snapshot.head_sha,
        "branch": snapshot.current_branch,
        "dirty": snapshot.dirty,
        "recoverable_paths": recoverable,
        "skipped_secret_paths": skipped_secrets,
        "applied": False,
        "preserved": False,
        "file_count": 0,
        "manifest_sha256": None,
    }
    if not recoverable:
        payload["reason"] = "no recoverable uncommitted files"
        return payload
    if not apply:
        payload["reason"] = "dry-run; pass apply to write the preservation bundle"
        return payload
    if dest.exists() and any(dest.iterdir()):
        raise WipPreserveError("WIP destination must be empty or absent")
    files_root = dest / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    entries = []
    for relative in recoverable:
        source = root / relative
        target = files_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        entries.append(
            {
                "path": relative,
                "sha256": sha256_file(source),
                "size_bytes": source.stat().st_size,
            }
        )
    manifest = {
        "schema_version": "1.0.0",
        "head_sha": snapshot.head_sha,
        "branch": snapshot.current_branch,
        "generated_at_utc": payload["generated_at_utc"],
        "entries": entries,
        "skipped_secret_paths": skipped_secrets,
        "source_files_deleted": False,
    }
    manifest_path = dest / "manifest.json"
    temporary = dest / "manifest.json.tmp"
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    temporary.replace(manifest_path)
    payload.update(
        {
            "applied": True,
            "preserved": True,
            "file_count": len(entries),
            "manifest_sha256": sha256_file(manifest_path),
            "reason": "recoverable uncommitted files preserved without mutating the source tree",
        }
    )
    return payload


def restore_uncommitted_work(
    bundle: Path,
    destination: Path,
    *,
    apply: bool = False,
    policy: RestoreTargetPolicy | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Restore a preservation bundle into an isolated destination. Never deletes secrets."""

    bundle = bundle.expanduser().resolve(strict=False)
    if policy is None:
        raise WipPreserveError("WIP restore requires an isolated RestoreTargetPolicy")
    try:
        dest = policy.resolve(destination)
    except ValueError as exc:
        raise WipPreserveError(str(exc)) from exc
    dest = _safe_destination(dest, workspace_root)
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise WipPreserveError("WIP bundle manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(manifest.get("entries") or [])
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "bundle": str(bundle),
        "destination": str(dest),
        "head_sha": manifest.get("head_sha"),
        "file_count": len(entries),
        "applied": False,
        "restored": False,
        "verified": False,
        "user_action_required": False,
    }
    if not apply:
        payload["reason"] = "dry-run; pass apply to write restored files"
        return payload
    dest.mkdir(parents=True, exist_ok=True)
    restored = []
    for entry in entries:
        relative = str(entry["path"]).replace("\\", "/")
        if _is_secret_path(relative) or has_traversal(relative):
            raise WipPreserveError(f"WIP restore refused secret or traversal path: {relative}")
        source = bundle / "files" / relative
        target = dest / relative
        if not source.is_file():
            raise WipPreserveError(f"WIP bundle file missing: {relative}")
        digest = sha256_file(source)
        if digest != entry.get("sha256"):
            raise WipPreserveError(f"WIP bundle digest mismatch: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored.append({"path": relative, "sha256": digest})
    payload.update(
        {
            "applied": True,
            "restored": True,
            "verified": True,
            "restored_paths": [item["path"] for item in restored],
            "reason": "WIP bundle restored with digest proof",
        }
    )
    return payload
