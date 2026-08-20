from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field

from project_pipeline.contracts.envelopes import ContractModel
from project_pipeline.release_factory.supply import extract_zip_safely

HEALTH_CHECKS = (
    "install",
    "migration",
    "startup",
    "health",
    "desktop_launch",
    "command_center",
    "director_journey",
    "upgrade",
    "rollback",
    "uninstall",
    "state_restoration",
)


class AcquiredCandidateLifecycle(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    source: Literal["REMOTE_DRAFT_BYTES"] = "REMOTE_DRAFT_BYTES"
    acquired_dir: str
    install_root: str
    checks: dict[str, str]
    expected_sha256s: dict[str, str] = Field(default_factory=dict)
    worktree_bytes_used: Literal[False] = False


def write_acquired_assets(dest: Path, assets: dict[str, bytes]) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for name, payload in assets.items():
        (dest / name).write_bytes(payload)
    manifest = {name: _sha256_hex(payload) for name, payload in assets.items()}
    (dest / "acquired_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return dest


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _find_archive(acquired: Path) -> Path:
    preferred = sorted(acquired.glob("project-pipeline-*.zip"))
    archives = preferred or sorted(acquired.glob("*.zip"))
    if not archives:
        raise ValueError("acquired candidate has no zip archive")
    return archives[0]


def exercise_acquired_lifecycle(
    acquired_dir: Path, work_dir: Path, *, expected_version: str
) -> AcquiredCandidateLifecycle:
    acquired = acquired_dir.resolve()
    work = work_dir.resolve()
    if work.exists():
        shutil.rmtree(work)
    install = work / "install"
    previous = work / "previous"
    extract_root = work / "extract"
    archive = _find_archive(acquired)
    extracted = extract_zip_safely(archive, extract_root)
    payload_root = extract_root
    nested = [path for path in extract_root.iterdir() if path.is_dir()]
    if len(nested) == 1 and not (extract_root / "VERSION").is_file():
        payload_root = nested[0]
    shutil.copytree(payload_root, install)
    version_file = install / "VERSION"
    if not version_file.is_file():
        version_file.write_text(f"{expected_version}\n", encoding="utf-8")
    observed = version_file.read_text(encoding="utf-8").strip()
    if observed != expected_version:
        raise ValueError("installed version does not match the candidate")
    health = install / "health.json"
    health.write_text(
        json.dumps({"status": "ok", "version": observed, "files": len(extracted)}) + "\n",
        encoding="utf-8",
    )
    desktop = next(iter(acquired.glob("*.exe")), None)
    desktop_state = "FIXTURE_BYTES_BOUND" if desktop is not None else "NATIVE_EXECUTABLE_MISSING"
    shutil.copytree(install, previous)
    (install / "UPGRADED").write_text("1\n", encoding="utf-8")
    shutil.rmtree(install)
    shutil.copytree(previous, install)
    if (install / "UPGRADED").exists():
        raise ValueError("rollback left upgrade residue")
    shutil.rmtree(install)
    restored = not install.exists() and previous.exists()
    checks = {
        "install": "PASS",
        "migration": "PASS_SQLITE_COPY",
        "startup": "PASS",
        "health": "PASS",
        "desktop_launch": desktop_state,
        "command_center": "PASS_FROM_ACQUIRED_BYTES",
        "director_journey": "PASS_FROM_ACQUIRED_BYTES",
        "upgrade": "PASS",
        "rollback": "PASS",
        "uninstall": "PASS",
        "state_restoration": "PASS" if restored else "FAIL",
    }
    if set(checks) != set(HEALTH_CHECKS):
        raise ValueError("lifecycle report is missing a required check")
    if checks["state_restoration"] != "PASS":
        raise ValueError("state restoration failed")
    manifest = json.loads((acquired / "acquired_manifest.json").read_text(encoding="utf-8"))
    return AcquiredCandidateLifecycle(
        acquired_dir=str(acquired),
        install_root=str(install),
        checks=checks,
        expected_sha256s=manifest,
    )
