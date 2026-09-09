"""Bind a content-addressed private control overlay to an exact public SHA/tree."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

OVERLAY_ENV = "PP_CONTROL_OVERLAY"
MANIFEST_NAME = "OVERLAY_MANIFEST.json"
REQUIRED_DOMAINS = ("instructions", "jira", "plans", "provenance")
EXTRA_BIND_PATHS = (
    "AGENTS.md",
    ".agents",
    "config/project_manifest.json",
    "docs/NAVIGATION.md",
    "docs/jira",
    "docs/CONTINUATION_PACKAGE.md",
    "docs/REQUIREMENT_CATALOG.md",
    "docs/STATUS_MODEL.md",
    "docs/engineering/pp380_disposition_generation.md",
    "docs/generated",
    "tests/test_instruction_system.py",
    "tests/test_domain_models.py",
    "evidence/EVIDENCE_LEDGER.jsonl",
)
FORBIDDEN_OVERLAY_NAMES = frozenset(
    {".env", ".venv", "venv", "node_modules", "Oracle", "oracle", "gold", "hidden"}
)


def inspect_source_identity(root: Path) -> dict[str, str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD", "HEAD^{tree}"],
        check=False,
        capture_output=True,
        text=True,
    )
    lines = [line.strip().lower() for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or len(lines) < 2:
        return {"sha": "", "tree": "", "ok": False}
    return {"sha": lines[0], "tree": lines[1], "ok": True}


def overlay_candidate(root: Path) -> Path | None:
    configured = os.environ.get(OVERLAY_ENV, "").strip()
    if configured:
        return Path(configured)
    local = root.resolve() / ".local" / "control_overlay"
    if (local / MANIFEST_NAME).is_file():
        return local
    return None


def load_overlay_manifest(overlay: Path) -> dict[str, Any] | None:
    path = overlay / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def overlay_digest(overlay: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(overlay.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        if any(part in FORBIDDEN_OVERLAY_NAMES for part in path.parts):
            continue
        hasher.update(path.relative_to(overlay).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def bound_overlay(root: Path) -> dict[str, Any]:
    """Return the overlay only when it is bound to this checkout's SHA/tree."""

    root = root.resolve()
    candidate = overlay_candidate(root)
    identity = inspect_source_identity(root)
    if candidate is None:
        return {
            "ok": False,
            "reason": "overlay_absent",
            "root": str(root),
            "identity": identity,
        }
    manifest = load_overlay_manifest(candidate)
    if not manifest:
        return {"ok": False, "reason": "overlay_manifest_missing", "overlay": str(candidate)}
    expected_sha = str(manifest.get("source_sha") or "").strip().lower()
    expected_tree = str(manifest.get("source_tree") or "").strip().lower()
    if expected_sha != identity.get("sha") or expected_tree != identity.get("tree"):
        return {
            "ok": False,
            "reason": "overlay_identity_mismatch",
            "overlay": str(candidate),
            "identity": identity,
            "manifest_sha": expected_sha,
            "manifest_tree": expected_tree,
        }
    missing = [name for name in REQUIRED_DOMAINS if not (candidate / name).exists()]
    if missing:
        return {
            "ok": False,
            "reason": "overlay_domains_missing",
            "missing": missing,
            "overlay": str(candidate),
        }
    return {
        "ok": True,
        "root": str(root),
        "overlay": str(candidate.resolve()),
        "identity": identity,
        "digest": str(manifest.get("digest") or overlay_digest(candidate)),
        "domains": list(REQUIRED_DOMAINS),
    }


def control_input_root(root: Path) -> Path:
    """Use a bound overlay for private control inputs; otherwise the source root."""

    decision = bound_overlay(root)
    if decision.get("ok"):
        return Path(str(decision["overlay"]))
    return root.resolve()


def locate_input(root: Path, relative: str) -> Path:
    """Resolve a control or source path, preferring a bound overlay."""

    overlay = control_input_root(root)
    candidate = overlay / relative
    if candidate.exists():
        return candidate
    return root.resolve() / relative


def _overlay_ignore(_directory: str, names: list[str]) -> set[str]:
    denied = set()
    for name in names:
        lowered = name.lower()
        if name in FORBIDDEN_OVERLAY_NAMES or lowered in {item.lower() for item in FORBIDDEN_OVERLAY_NAMES}:
            denied.add(name)
        if lowered in {".env", ".venv", "venv", "__pycache__", ".git"}:
            denied.add(name)
        if lowered.endswith((".sqlite3", ".db", ".pyc")):
            denied.add(name)
    return denied


def bind_overlay_from_source(
    *,
    source_root: Path,
    overlay_root: Path,
    control_source: Path,
    source_sha: str,
    source_tree: str,
    extra_domains: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Copy a read-only control overlay and bind it to an exact public SHA/tree."""

    overlay_root = overlay_root.resolve()
    overlay_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    domains = list(REQUIRED_DOMAINS) + [item for item in extra_domains if item not in REQUIRED_DOMAINS]
    for domain in domains:
        origin = control_source / domain
        if not origin.exists():
            continue
        destination = overlay_root / domain
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(origin, destination, ignore=_overlay_ignore, dirs_exist_ok=False)
        copied.append(domain)
    for relative in EXTRA_BIND_PATHS:
        origin = control_source / relative
        if not origin.exists():
            continue
        destination = overlay_root / relative
        if origin.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(origin, destination, ignore=_overlay_ignore)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, destination)
        copied.append(relative)
    digest = overlay_digest(overlay_root)
    manifest = {
        "schema_version": "1.0.0",
        "source_sha": source_sha.lower(),
        "source_tree": source_tree.lower(),
        "source_root": str(source_root.resolve()),
        "control_source": str(control_source.resolve()),
        "digest": digest,
        "domains": copied,
        "read_only": True,
    }
    (overlay_root / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    refresh_instruction_manifest_hashes(overlay_root, source_root)
    digest = overlay_digest(overlay_root)
    manifest["digest"] = digest
    (overlay_root / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"ok": True, "overlay": str(overlay_root), "manifest": manifest}


def refresh_instruction_manifest_hashes(overlay_root: Path, source_root: Path) -> None:
    """Bind overlay instruction-pack hashes to actual overlay/public bytes for this SHA."""

    path = overlay_root / "instructions" / "INSTRUCTION_MANIFEST.json"
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("files")
    if not isinstance(records, list):
        return
    updated: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or not record.get("path"):
            updated.append(record)
            continue
        relative = str(record["path"])
        overlay_file = overlay_root / relative
        source_file = source_root / relative
        if overlay_file.is_file():
            updated.append(record)
            continue
        if not source_file.is_file():
            updated.append(record)
            continue
        digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        item = dict(record)
        item["sha256"] = digest
        item["size_bytes"] = source_file.stat().st_size
        updated.append(item)
    payload["files"] = updated
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
