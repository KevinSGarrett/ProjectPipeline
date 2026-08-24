"""Build and provenance-bind the native desktop artifacts for one campaign candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.campaign import inspect_worktree_identity  # noqa: E402
from project_pipeline.github_steward.asset_names import canonical_release_asset_name  # noqa: E402
from project_pipeline.release_factory.bundle import BoundArtifact  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_payload(path: Path, *, kind: str, sha: str, tree: str) -> dict[str, Any]:
    return BoundArtifact(
        kind=kind,
        name=path.name,
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
        source_sha=sha,
        source_tree=tree,
    ).model_dump(mode="json")


def _sidecar_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".candidate.json")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("desktop-native-build-failed")


def build_artifacts(
    *, root: Path, output_dir: Path, expected_sha: str, expected_tree: str
) -> dict[str, Any]:
    root = root.resolve()
    output = output_dir.resolve()
    identity = inspect_worktree_identity(root)
    if (
        not identity.get("ok")
        or identity.get("dirty")
        or identity.get("sha") != expected_sha
        or identity.get("tree") != expected_tree
    ):
        raise RuntimeError("desktop-build-candidate-identity-drift")
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("desktop-build-output-conflict")
    output.mkdir(parents=True, exist_ok=True)

    frontend = root / "apps" / "command_center"
    if not (frontend / "package-lock.json").is_file():
        raise RuntimeError("desktop-build-lockfile-missing")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("desktop-build-npm-unavailable")
    environment = dict(os.environ)
    environment["CARGO_TARGET_DIR"] = str(output / "cargo-target")
    _run([npm, "ci"], cwd=frontend, environment=environment)
    _run([npm, "run", "tauri:build", "--", "--", "--locked"], cwd=frontend, environment=environment)

    release_dir = output / "cargo-target" / "release"
    executable = release_dir / "project-pipeline-command-center.exe"
    installers = sorted(
        path for path in (release_dir / "bundle" / "nsis").glob("*setup.exe") if path.is_file()
    )
    if not executable.is_file() or len(installers) != 1:
        raise RuntimeError("desktop-build-artifacts-missing")
    staged_executable = output / canonical_release_asset_name(executable.name)
    staged_installer = output / canonical_release_asset_name(installers[0].name)
    shutil.copy2(executable, staged_executable)
    shutil.copy2(installers[0], staged_installer)
    artifacts = {
        "windows_executable": _artifact_payload(
            staged_executable, kind="windows_executable", sha=expected_sha, tree=expected_tree
        ),
        "windows_installer": _artifact_payload(
            staged_installer, kind="windows_installer", sha=expected_sha, tree=expected_tree
        ),
    }
    for item in artifacts.values():
        _write_json(_sidecar_path(output / str(item["name"])), item)
    final_identity = inspect_worktree_identity(root)
    if (
        not final_identity.get("ok")
        or final_identity.get("dirty")
        or final_identity.get("sha") != expected_sha
        or final_identity.get("tree") != expected_tree
    ):
        raise RuntimeError("desktop-build-candidate-identity-drift")
    payload = {
        "state": "BUILT",
        "real_native_build": True,
        "source_sha": expected_sha,
        "source_tree": expected_tree,
        "artifacts": artifacts,
    }
    _write_json(output / "desktop_build.json", payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-tree", required=True)
    args = parser.parse_args(argv)
    try:
        payload = build_artifacts(
            root=args.repository_root,
            output_dir=args.output_dir,
            expected_sha=args.expected_sha,
            expected_tree=args.expected_tree,
        )
    except Exception as exc:
        print(json.dumps({"desktop_build": {"state": "FAILED"}, "reason": str(exc)}))
        return 1
    print(json.dumps({"desktop_build": payload}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
