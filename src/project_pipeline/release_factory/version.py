from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field

from project_pipeline.contracts.envelopes import ContractModel
from project_pipeline.release_hardening.candidate import resolve_candidate_identity

VERSION_SOURCE_MISMATCH = "VERSION_SOURCE_MISMATCH"
_CARGO_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


class ReleaseVersionAuthority(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    bundle_version: str
    desktop_version: str
    source_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    source_tree: str = Field(pattern=r"^[a-f0-9]{40}$")
    sources: dict[str, str]
    dual_identity: bool
    tag_name: str


def _read_json_version(path: Path, field: str) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = str(payload.get(field) or "").strip()
    if not value:
        raise ValueError(f"{path.as_posix()} is missing {field}")
    return value


def _cargo_package_version(path: Path) -> str:
    match = _CARGO_VERSION.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"{path.as_posix()} is missing package version")
    return match.group(1)


def _python_package_version(root: Path) -> str:
    text = (root / "src/project_pipeline/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if match is None:
        raise ValueError("python package __version__ is missing")
    return match.group(1)


def collect_version_sources(root: Path) -> dict[str, str]:
    root = root.resolve()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return {
        "pyproject": str(project["version"]),
        "platform": _read_json_version(
            root / "config/version_compatibility.json", "platform_version"
        ),
        "python_package": _python_package_version(root),
        "command_center_npm": _read_json_version(
            root / "apps/command_center/package.json", "version"
        ),
        "tauri": _read_json_version(
            root / "apps/desktop_shell/src-tauri/tauri.conf.json", "version"
        ),
        "cargo": _cargo_package_version(root / "apps/desktop_shell/src-tauri/Cargo.toml"),
    }


def resolve_release_version_authority(root: Path) -> ReleaseVersionAuthority:
    root = root.resolve()
    sources = collect_version_sources(root)
    python_group = {sources["pyproject"], sources["platform"], sources["python_package"]}
    desktop_group = {
        sources["command_center_npm"],
        sources["tauri"],
        sources["cargo"],
    }
    if len(python_group) != 1:
        raise ValueError(
            f"{VERSION_SOURCE_MISMATCH}: python/platform versions {sorted(python_group)}"
        )
    if len(desktop_group) != 1:
        raise ValueError(f"{VERSION_SOURCE_MISMATCH}: desktop versions {sorted(desktop_group)}")
    bundle_version = sources["platform"]
    desktop_version = next(iter(desktop_group))
    source_sha, source_tree = resolve_candidate_identity(root)
    return ReleaseVersionAuthority(
        bundle_version=bundle_version,
        desktop_version=desktop_version,
        source_sha=source_sha,
        source_tree=source_tree,
        sources=sources,
        dual_identity=bundle_version != desktop_version,
        tag_name=f"v{bundle_version}-rc.{source_sha[:12]}",
    )
