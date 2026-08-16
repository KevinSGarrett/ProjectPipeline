from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.io import iter_repository_files, write_json

MANIFEST_EXCLUSIONS = frozenset(
    {
        "PROJECT_MANIFEST.json",
        "FILE_MANIFEST.sha256",
        "docs/generated/REPOSITORY_MAP.json",
        "docs/generated/REPOSITORY_MAP.md",
    }
)
ENV_TEMPLATE_NAMES = frozenset({".env.example", ".env.sample", ".env.template"})
LOCAL_SECRET_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx"})


def _canonical_manifest_content(path: Path) -> bytes:
    content = path.read_bytes()
    if b"\0" in content:
        return content
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    return content.replace(b"\r\n", b"\n")


def is_local_only_manifest_path(relative: str) -> bool:
    path = Path(relative)
    name = path.name
    if path.parts and path.parts[0].startswith(".codex"):
        return True
    if name == ".env" or (name.startswith(".env.") and name not in ENV_TEMPLATE_NAMES):
        return True
    return path.suffix.lower() in LOCAL_SECRET_SUFFIXES


def build_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    files: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    for path in iter_repository_files(root, excluded_relative_paths=MANIFEST_EXCLUSIONS):
        relative = path.relative_to(root).as_posix()
        if is_local_only_manifest_path(relative):
            continue
        content = _canonical_manifest_content(path)
        digest = hashlib.sha256(content).hexdigest()
        size = len(content)
        files.append({"path": relative, "size_bytes": size, "sha256": digest})
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "1.0.0",
        "project_id": "PROJECT-PIPELINE",
        "root_name": root.name,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "aggregate_sha256": aggregate.hexdigest(),
        "files": files,
        "exclusions": sorted(MANIFEST_EXCLUSIONS),
        "local_only_exclusion_rules": [
            ".env and non-template .env.* files",
            "private key/certificate files: *.pem, *.key, *.p12, *.pfx",
            "local assistant/runtime/upstream directories from project_pipeline.io",
        ],
        "content_canonicalization": "UTF-8 CRLF is normalized to LF; binary content is hashed unchanged",
    }


def write_manifest(root: Path) -> dict[str, Any]:
    manifest = build_manifest(root)
    write_json(root / "PROJECT_MANIFEST.json", manifest)
    lines = [f"{item['sha256']}  {item['path']}" for item in manifest["files"]]
    (root / "FILE_MANIFEST.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def verify_manifest(root: Path) -> list[str]:
    path = root / "PROJECT_MANIFEST.json"
    if not path.exists():
        return ["PROJECT_MANIFEST.json is missing"]
    import json

    recorded = json.loads(path.read_text(encoding="utf-8"))
    current = build_manifest(root)
    errors: list[str] = []
    recorded_files = {item["path"]: item for item in recorded.get("files", [])}
    current_files = {item["path"]: item for item in current["files"]}
    for missing in sorted(recorded_files.keys() - current_files.keys()):
        errors.append(f"Manifest file missing from repository: {missing}")
    for added in sorted(current_files.keys() - recorded_files.keys()):
        errors.append(f"Repository file missing from manifest: {added}")
    for common in sorted(recorded_files.keys() & current_files.keys()):
        if recorded_files[common]["sha256"] != current_files[common]["sha256"]:
            errors.append(f"Manifest digest mismatch: {common}")
    if recorded.get("aggregate_sha256") != current.get("aggregate_sha256"):
        errors.append("Manifest aggregate digest mismatch")
    return errors
