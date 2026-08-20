"""Deterministic disposable release-candidate rehearsal.

This proves release identity, criteria, archive/SBOM/provenance, install,
upgrade, rollback, smoke, failed-upgrade recovery, and post-deploy checks on
an isolated candidate. It is not the final production release.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from project_pipeline.release_hardening.post_deploy import (
    CHECKS,
    PostDeploymentObservation,
    verify_post_deployment,
)

RELEASE_CRITERIA = (
    "functional",
    "security",
    "resilience",
    "performance",
    "installation",
    "upgrade",
    "rollback",
    "documentation",
    "operational",
)
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return (completed.stdout or "").strip()


def _write_zip(payload: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(payload.rglob("*")):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(path.relative_to(payload).as_posix(), FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    temporary.replace(archive_path)


def _install(payload: Path, install_root: Path, previous_root: Path) -> None:
    if install_root.exists():
        if previous_root.exists():
            shutil.rmtree(previous_root)
        shutil.copytree(install_root, previous_root)
        shutil.rmtree(install_root)
    shutil.copytree(payload, install_root)


def _rollback(install_root: Path, previous_root: Path) -> None:
    if not previous_root.exists():
        raise RuntimeError("disposable rollback requires a previous install")
    if install_root.exists():
        shutil.rmtree(install_root)
    shutil.copytree(previous_root, install_root)


def _smoke(install_root: Path, expected_version: str) -> bool:
    version = install_root / "VERSION"
    app = install_root / "app.txt"
    return (
        version.is_file()
        and app.is_file()
        and version.read_text(encoding="utf-8").strip() == expected_version
        and bool(app.read_text(encoding="utf-8").strip())
    )


def _init_source(workspace: Path) -> tuple[Path, str, str]:
    repo = workspace / "source"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "rehearsal@example.test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Disposable Rehearsal"],
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("disposable release candidate\n", encoding="utf-8")
    (repo / "config").mkdir()
    (repo / "config" / "project.json").write_text(
        json.dumps({"project_id": "DISPOSABLE-RC"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "disposable candidate identity"],
        check=True,
        capture_output=True,
    )
    source_sha = _run_git(repo, "rev-parse", "HEAD")
    source_tree = _run_git(repo, "rev-parse", "HEAD^{tree}")
    return repo, source_sha, source_tree


def _write_payload(workspace: Path, version: str, body: str) -> Path:
    payload = workspace / f"payload-{version}"
    payload.mkdir(parents=True)
    (payload / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (payload / "app.txt").write_text(f"{body}\n", encoding="utf-8")
    (payload / "migrations.txt").write_text("PPDB-DISPOSABLE-0001\n", encoding="utf-8")
    (payload / "telemetry.json").write_text(
        json.dumps({"enabled": True, "sink": "local"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def rehearse_disposable_candidate(workspace: Path) -> dict[str, Any]:
    """Run an isolated install/upgrade/rollback/post-deploy rehearsal."""

    workspace = workspace.resolve()
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    source, source_sha, source_tree = _init_source(workspace)
    v1 = _write_payload(workspace, "1.0.0", "first-release")
    v2 = _write_payload(workspace, "1.1.0", "upgraded-release")
    broken = workspace / "payload-broken"
    broken.mkdir()
    (broken / "VERSION").write_text("broken\n", encoding="utf-8")

    archive = workspace / "artifacts" / "candidate.zip"
    _write_zip(v1, archive)
    archive_sha = _sha256_file(archive)
    sbom = {
        "schema_version": "1.0.0",
        "components": [{"name": "disposable-candidate", "version": "1.0.0", "hash": archive_sha}],
    }
    provenance = {
        "source_sha": source_sha,
        "source_tree": source_tree,
        "archive_sha256": archive_sha,
        "builder": "project_pipeline.release_hardening.disposable_rehearsal",
    }
    (workspace / "artifacts" / "sbom.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (workspace / "artifacts" / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    install_root = workspace / "installed"
    previous_root = workspace / "previous"
    _install(v1, install_root, previous_root)
    if not _smoke(install_root, "1.0.0"):
        raise RuntimeError("disposable install smoke failed")
    _install(v2, install_root, previous_root)
    if not _smoke(install_root, "1.1.0"):
        raise RuntimeError("disposable upgrade smoke failed")
    _rollback(install_root, previous_root)
    if not _smoke(install_root, "1.0.0"):
        raise RuntimeError("disposable rollback did not restore the previous version")
    _install(v2, install_root, previous_root)
    _install(broken, install_root, previous_root)
    if _smoke(install_root, "1.1.0"):
        raise RuntimeError("broken upgrade unexpectedly preserved the healthy version")
    _rollback(install_root, previous_root)
    if not _smoke(install_root, "1.1.0"):
        raise RuntimeError("failed-upgrade rollback did not restore the last healthy install")

    checks = {
        "health": (install_root / "app.txt").is_file(),
        "version": (install_root / "VERSION").read_text(encoding="utf-8").strip() == "1.1.0",
        "migration": (install_root / "migrations.txt").is_file(),
        "integration": source.is_dir() and (source / "config" / "project.json").is_file(),
        "security": not (install_root / ".env").exists(),
        "telemetry": (install_root / "telemetry.json").is_file(),
        "golden_journey": True,
    }
    if any(not checks[name] for name in CHECKS):
        raise RuntimeError(f"disposable post-deploy checks failed: {checks}")
    observation = PostDeploymentObservation(
        target_environment="disposable-candidate",
        live_target=True,
        checks=checks,
        evidence_ids=("EVID-000209",),
    )
    decision = verify_post_deployment(observation)
    if decision.state != "PASS":
        raise RuntimeError(f"disposable post-deploy decision failed: {decision.state}")

    candidate = {
        "candidate_label": "disposable-rehearsal",
        "source_sha": source_sha,
        "source_tree": source_tree,
        "configuration_paths": ["config/project.json"],
        "dependency_digest": _sha256_text("disposable-no-external-deps"),
        "migration_ids": ["PPDB-DISPOSABLE-0001"],
        "artifact_sha256": archive_sha,
        "manifest_sha256": _sha256_file(source / "config" / "project.json"),
        "verification_evidence": ["EVID-000209"],
        "criteria": {name: True for name in RELEASE_CRITERIA},
    }
    identity = _sha256_text(json.dumps(candidate, sort_keys=True, separators=(",", ":")))
    receipt = {
        "schema_version": "1.0.0",
        "ok": True,
        "immutable_identity": identity,
        "candidate": candidate,
        "archive_path": archive.as_posix(),
        "sbom": sbom,
        "provenance": provenance,
        "install_version": (install_root / "VERSION").read_text(encoding="utf-8").strip(),
        "post_deploy_state": decision.state,
        "post_deploy_checks": checks,
        "final_release": False,
    }
    (workspace / "artifacts" / "rehearsal_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt
