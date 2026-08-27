"""Build and provenance-bind the native desktop artifacts for one campaign candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.campaign import inspect_worktree_identity  # noqa: E402
from project_pipeline.github_steward.asset_names import canonical_release_asset_name  # noqa: E402
from project_pipeline.release_factory.bundle import BoundArtifact  # noqa: E402
from project_pipeline.release_hardening import disposable_rehearsal as _ra  # noqa: E402
from project_pipeline.resilience.host_safety import require_safe_local_host  # noqa: E402

_GNU_TARGET = "x86_64-pc-windows-gnu"
_MSVC_TARGET = "x86_64-pc-windows-msvc"
_GNU_GCC = "x86_64-w64-mingw32-gcc.exe"
_PORTABLE_BUNDLE_MANIFEST = "project-pipeline-portable-manifest.json"
_GNU_PORTABLE_DEPENDENCIES = ("WebView2Loader.dll",)


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


def _stage_portable_desktop_bundle(
    executable: Path,
    *,
    release_dir: Path,
    output: Path,
    build_target: str,
) -> Path:
    """Create the single portable desktop release asset with every loader dependency.

    GNU-linked Tauri binaries require ``WebView2Loader.dll`` next to the PE at
    process start. The release asset is therefore a deterministic portable ZIP,
    not an orphaned executable that can only work in the build directory.
    """

    portable = output / canonical_release_asset_name(f"{executable.stem}-portable.zip")
    required_dependencies = _GNU_PORTABLE_DEPENDENCIES if build_target == _GNU_TARGET else ()
    dependency_paths = tuple(release_dir / dependency for dependency in required_dependencies)
    missing = [path.name for path in dependency_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"desktop-build-portable-dependency-missing:{','.join(missing)}")
    manifest = {
        "schema_version": "1.0.0",
        "entrypoint": executable.name,
        "required_files": list(required_dependencies),
        "build_target": build_target,
    }
    entries = [(executable.name, executable.read_bytes())]
    entries.extend((path.name, path.read_bytes()) for path in dependency_paths)
    entries.append(
        (
            _PORTABLE_BUNDLE_MANIFEST,
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    )
    temporary = portable.with_suffix(portable.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(entries, key=lambda item: item[0].casefold()):
            info = zipfile.ZipInfo(name, _ra.FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    temporary.replace(portable)
    return portable


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


def _winget_winlibs_bin(environment: dict[str, str]) -> Path | None:
    """Locate the user-scoped WinLibs package without persisting a toolchain path."""

    local_app_data = environment.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    for candidate in sorted(package_root.glob("BrechtSanders.WinLibs.POSIX.UCRT_*/mingw64/bin")):
        if (candidate / _GNU_GCC).is_file():
            return candidate
    return None


def _copy_gnu_toolchain_to_build_workspace(source_bin: Path, workspace: Path) -> tuple[Path, Path]:
    """Copy a GNU toolchain whose embedded prefix contains a space."""

    anchor = workspace.anchor
    if not anchor or " " in anchor:
        raise RuntimeError("desktop-build-gnu-toolchain-workspace-unavailable")
    staging_root = Path(tempfile.mkdtemp(prefix="projectpipeline-desktop-toolchain-", dir=anchor))
    try:
        destination_root = staging_root / "mingw64"
        shutil.copytree(source_bin.parent, destination_root)
        copied_bin = destination_root / "bin"
        if not (copied_bin / _GNU_GCC).is_file():
            raise RuntimeError("desktop-build-gnu-linker-unavailable")
        return copied_bin, staging_root
    except Exception:
        shutil.rmtree(staging_root)
        raise


def _gnu_toolchain_path_entry(path: Path, *, workspace: Path) -> tuple[Path, Path | None]:
    """Provide GNU ld a toolchain prefix without Windows path separators."""

    if " " not in str(path):
        return path, None
    return _copy_gnu_toolchain_to_build_workspace(path, workspace)


def _prepare_native_build_environment(
    environment: dict[str, str],
    *,
    workspace: Path,
) -> tuple[dict[str, str], str, str, Path | None]:
    """Choose a native Windows toolchain and return its isolated build environment."""

    configured = dict(environment)
    requested_target = configured.get("PROJECT_PIPELINE_DESKTOP_TARGET", "").strip()
    if requested_target and requested_target not in {_GNU_TARGET, _MSVC_TARGET}:
        raise RuntimeError("desktop-build-target-unsupported")

    path_value = configured.get("PATH", "")
    target = requested_target or (
        _MSVC_TARGET if shutil.which("link.exe", path=path_value) else _GNU_TARGET
    )
    if target == _MSVC_TARGET:
        if not shutil.which("link.exe", path=path_value):
            raise RuntimeError("desktop-build-msvc-linker-unavailable")
        return configured, target, "MSVC link.exe", None

    compiler = shutil.which(_GNU_GCC, path=path_value)
    if compiler:
        path_entry, toolchain_staging_root = _gnu_toolchain_path_entry(
            Path(compiler).parent, workspace=workspace
        )
    else:
        winlibs_bin = _winget_winlibs_bin(configured)
        if winlibs_bin is None:
            raise RuntimeError("desktop-build-gnu-linker-unavailable")
        path_entry, toolchain_staging_root = _gnu_toolchain_path_entry(
            winlibs_bin, workspace=workspace
        )
    configured["PATH"] = str(path_entry) + os.pathsep + path_value
    compiler_path = path_entry / _GNU_GCC
    configured["CARGO_BUILD_TARGET"] = _GNU_TARGET
    return configured, target, str(compiler_path), toolchain_staging_root


def _gnu_rust_toolchain(root: Path) -> str:
    """Derive the installed GNU toolchain from the repository's pinned Rust channel."""

    toolchain_path = root / "rust-toolchain.toml"
    try:
        payload = tomllib.loads(toolchain_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError("desktop-build-rust-toolchain-unavailable") from error
    toolchain = payload.get("toolchain")
    channel = toolchain.get("channel") if isinstance(toolchain, dict) else None
    if not isinstance(channel, str) or not channel.strip():
        raise RuntimeError("desktop-build-rust-toolchain-unavailable")
    suffix = "-x86_64-pc-windows-gnu"
    return channel if channel.endswith(suffix) else f"{channel}{suffix}"


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
    host_safety = require_safe_local_host(root)
    output_existed = output.exists()
    output.mkdir(parents=True, exist_ok=True)
    toolchain_staging_root: Path | None = None
    try:
        frontend = root / "apps" / "command_center"
        if not (frontend / "package-lock.json").is_file():
            raise RuntimeError("desktop-build-lockfile-missing")
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("desktop-build-npm-unavailable")
        environment, build_target, compiler, toolchain_staging_root = (
            _prepare_native_build_environment(dict(os.environ), workspace=output)
        )
        rust_toolchain = None
        if build_target == _GNU_TARGET:
            rust_toolchain = _gnu_rust_toolchain(root)
            environment["RUSTUP_TOOLCHAIN"] = rust_toolchain
        environment["CARGO_TARGET_DIR"] = str(output / "cargo-target")
        _run([npm, "ci"], cwd=frontend, environment=environment)
        tauri_command = [npm, "run", "tauri:build", "--"]
        if build_target != _MSVC_TARGET:
            tauri_command.extend(["--target", build_target])
        tauri_command.extend(["--", "--locked"])
        _run(tauri_command, cwd=frontend, environment=environment)
        if toolchain_staging_root is not None:
            shutil.rmtree(toolchain_staging_root)
            toolchain_staging_root = None

        release_dir = output / "cargo-target"
        if build_target != _MSVC_TARGET:
            release_dir = release_dir / build_target
        release_dir = release_dir / "release"
        executable = release_dir / "project-pipeline-command-center.exe"
        installers = sorted(
            path for path in (release_dir / "bundle" / "nsis").glob("*setup.exe") if path.is_file()
        )
        if not executable.is_file() or len(installers) != 1:
            raise RuntimeError("desktop-build-artifacts-missing")
        staged_executable = _stage_portable_desktop_bundle(
            executable,
            release_dir=release_dir,
            output=output,
            build_target=build_target,
        )
        staged_installer = output / canonical_release_asset_name(installers[0].name)
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
            "build_target": build_target,
            "compiler": compiler,
            "rust_toolchain": rust_toolchain,
            "host_safety": host_safety,
            "source_sha": expected_sha,
            "source_tree": expected_tree,
            "artifacts": artifacts,
        }
        _write_json(output / "desktop_build.json", payload)
        return payload
    except Exception:
        if toolchain_staging_root is not None and toolchain_staging_root.exists():
            shutil.rmtree(toolchain_staging_root)
        if not output_existed:
            shutil.rmtree(output)
        raise


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
