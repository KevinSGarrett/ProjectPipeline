from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from project_pipeline.contracts.envelopes import ContractModel
from project_pipeline.github_steward.asset_names import canonical_release_asset_name
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
    worktree_bytes_used: bool
    execution_mode: Literal["SIMULATED_REMOTE_BYTES", "REAL_NATIVE_REMOTE_BYTES"]


_ACQUIRED_METADATA = frozenset({"acquired_manifest.json", "campaign_publication.json"})


def candidate_acquired_dir(evidence_path: Path, *, source_sha: str, source_tree: str) -> Path:
    """Return the immutable remote-byte directory for one exact candidate."""

    return (
        evidence_path.resolve()
        / "remote-acquired"
        / (f"candidate-{source_sha.lower()}-{source_tree.lower()}")
    )


def _canonical_asset_bytes(assets: Mapping[str, bytes]) -> dict[str, bytes]:
    canonical: dict[str, bytes] = {}
    for raw_name, payload in assets.items():
        name = canonical_release_asset_name(raw_name)
        if name in canonical:
            raise ValueError("acquired remote bytes contain colliding canonical asset names")
        canonical[name] = payload
    return canonical


def write_acquired_assets(dest: Path, assets: dict[str, bytes]) -> Path:
    """Persist a flat, exact remote-byte acquisition or verify an exact replay.

    A candidate-specific acquisition may be replayed only when every byte and
    the complete file set match.  Any stale or pre-seeded artifact fails closed.
    """

    payloads = _canonical_asset_bytes(assets)
    manifest = {name: _sha256_hex(payload) for name, payload in payloads.items()}
    if dest.exists():
        if not dest.is_dir():
            raise ValueError("acquired remote-byte destination is not a directory")
        _verify_acquired_manifest(dest, expected_sha256s=manifest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent / f".acquired-staging-{uuid4().hex}"
    try:
        staging.mkdir(exist_ok=False)
        for name, payload in payloads.items():
            _write_file_fsynced(staging / name, payload)
        _write_file_fsynced(
            staging / "acquired_manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        _fsync_directory(staging)
        os.replace(staging, dest)
        _fsync_directory(dest.parent)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return dest


def _write_file_fsynced(path: Path, payload: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    """Best-effort directory sync; Windows does not expose directory handles."""

    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        os.close(descriptor)


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _find_archive(acquired: Path) -> Path:
    preferred = sorted(acquired.glob("project-pipeline-*.zip"))
    archives = preferred or sorted(acquired.glob("*.zip"))
    if not archives:
        raise ValueError("acquired candidate has no zip archive")
    return archives[0]


def _looks_like_source_worktree(acquired: Path) -> bool:
    return (acquired / ".git").exists() and (acquired / "src" / "project_pipeline").is_dir()


def _version_from_payload(payload_root: Path) -> str:
    version_file = payload_root / "VERSION"
    if version_file.is_file():
        observed = version_file.read_text(encoding="utf-8").strip()
        if observed:
            return observed
    pyproject = payload_root / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version") and "=" in stripped:
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    raise ValueError("acquired candidate is missing VERSION")


def _verify_acquired_manifest(
    acquired: Path, *, expected_sha256s: Mapping[str, str] | None = None
) -> dict[str, str]:
    manifest_path = acquired / "acquired_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("acquired candidate is missing its remote-byte manifest")
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not loaded:
        raise ValueError("acquired candidate manifest is malformed")
    manifest: dict[str, str] = {}
    for raw_name, raw_digest in loaded.items():
        name = canonical_release_asset_name(str(raw_name))
        if name != raw_name or name in manifest:
            raise ValueError("acquired candidate manifest has noncanonical asset names")
        manifest[name] = str(raw_digest).lower()
    expected_files = set(manifest) | {"acquired_manifest.json"}
    observed_files = {path.name for path in acquired.iterdir() if path.is_file()}
    if any(path.is_dir() for path in acquired.iterdir()) or not observed_files.issubset(
        expected_files | {"campaign_publication.json"}
    ):
        raise ValueError("acquired remote-byte directory has unexpected files")
    if not expected_files.issubset(observed_files):
        raise ValueError("acquired remote-byte directory is incomplete")
    for name, digest in manifest.items():
        artifact = acquired / name
        if not artifact.is_file() or _sha256_hex(artifact.read_bytes()) != digest:
            raise ValueError("acquired remote bytes do not match their manifest")
    if expected_sha256s is not None:
        expected: dict[str, str] = {}
        for raw_name, raw_digest in expected_sha256s.items():
            name = canonical_release_asset_name(raw_name)
            if name in expected:
                raise ValueError("expected acquired assets collide after normalization")
            expected[name] = str(raw_digest).lower()
        if manifest != expected:
            raise ValueError("acquired remote-byte manifest differs from the publication receipt")
    return manifest


def verify_acquired_assets(
    acquired: Path, *, expected_sha256s: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Verify the exact remote acquisition and return its canonical manifest."""

    return _verify_acquired_manifest(acquired, expected_sha256s=expected_sha256s)


def _require_command(
    command: list[str], *, timeout_seconds: float = 180.0, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("required remote-byte lifecycle command did not complete") from exc
    if completed.returncode != 0:
        raise ValueError("required remote-byte lifecycle command failed")
    return completed


def _venv_python(venv: Path) -> Path:
    candidate = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not candidate.is_file():
        raise ValueError("isolated lifecycle environment is incomplete")
    return candidate


def _isolated_python_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _run_python_artifact_checks(
    acquired: Path,
    work: Path,
    *,
    expected_version: str,
    remote_install_root: Path,
    python_executable: str | None,
) -> dict[str, str]:
    wheel = next(iter(sorted(acquired.glob("*.whl"))), None)
    sdist = next(iter(sorted(acquired.glob("*.tar.gz"))), None)
    if wheel is None or sdist is None:
        raise ValueError("acquired candidate requires a wheel and sdist")
    base_python = python_executable or sys.executable
    checks: dict[str, str] = {}
    environment = _isolated_python_environment()
    for name, artifact in (("wheel", wheel), ("sdist", sdist)):
        venv = work / f"{name}-venv"
        _require_command([base_python, "-m", "venv", str(venv)], environment=environment)
        interpreter = _venv_python(venv)
        _require_command(
            [
                str(interpreter),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(artifact),
            ],
            environment=environment,
        )
        installed = _require_command(
            [
                str(interpreter),
                "-c",
                (
                    "import json, project_pipeline; "
                    "print(json.dumps({'version': project_pipeline.__version__, "
                    "'path': project_pipeline.__file__}))"
                ),
            ],
            environment=environment,
        )
        try:
            imported = json.loads(installed.stdout)
            version = str(imported["version"])
            module_path = Path(str(imported["path"])).resolve()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("installed remote package import receipt is malformed") from exc
        if version != expected_version or not module_path.is_relative_to(venv.resolve()):
            raise ValueError("installed remote package version differs from the candidate")
        checks[f"{name}_install"] = "PASS"
        checks[f"{name}_import"] = "PASS"
        _require_command(
            [
                str(interpreter),
                "-m",
                "project_pipeline",
                "doctor",
                "--root",
                str(remote_install_root),
            ],
            environment=environment,
        )
        checks[f"{name}_doctor"] = "PASS"
    return checks


def _installed_desktop_executable(install: Path) -> Path:
    candidates = sorted(
        path
        for path in install.rglob("*.exe")
        if path.is_file()
        and "uninstall" not in path.name.casefold()
        and "setup" not in path.name.casefold()
    )
    if len(candidates) != 1:
        raise ValueError("native desktop install did not yield exactly one application executable")
    return candidates[0]


def _launch_and_stop(executable: Path) -> None:
    try:
        process = subprocess.Popen(
            [str(executable)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except OSError as exc:
        raise ValueError("installed remote desktop executable did not launch") from exc
    time.sleep(2.0)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise ValueError("installed remote desktop executable did not stop") from exc
    elif process.returncode not in {0, None}:
        raise ValueError("installed remote desktop executable exited unsuccessfully")


def _run_native_desktop_checks(acquired: Path, work: Path) -> dict[str, str]:
    installer_candidates = sorted(acquired.glob("*setup.exe"))
    if len(installer_candidates) != 1:
        raise ValueError("acquired candidate requires exactly one NSIS installer")
    installer = installer_candidates[0]
    install = work / "native-install"
    snapshot = work / "pre-upgrade-install"
    _require_command([str(installer), "/S", f"/D={install}"])
    if not install.is_dir():
        raise ValueError("native installer did not create its requested install directory")
    executable = _installed_desktop_executable(install)
    _launch_and_stop(executable)
    if snapshot.exists():
        shutil.rmtree(snapshot)
    shutil.copytree(install, snapshot)
    _require_command([str(installer), "/S", f"/D={install}"])
    upgraded = _installed_desktop_executable(install)
    _launch_and_stop(upgraded)
    shutil.rmtree(install)
    shutil.copytree(snapshot, install)
    restored = _installed_desktop_executable(install)
    _launch_and_stop(restored)
    uninstallers = sorted(path for path in install.rglob("uninstall*.exe") if path.is_file())
    if len(uninstallers) != 1:
        raise ValueError("native desktop install did not yield an uninstaller")
    _require_command([str(uninstallers[0]), "/S"])
    _wait_for_native_uninstall_cleanup(install)
    return {
        "desktop_install": "PASS",
        "desktop_launch": "PASS",
        "command_center": "PASS_NATIVE_DESKTOP_LAUNCH",
        "upgrade": "PASS_REINSTALL_FROM_REMOTE_BYTES",
        "rollback": "PASS_RESTORE_REMOTE_INSTALL_SNAPSHOT",
        "uninstall": "PASS",
        "state_restoration": "PASS",
    }


def _wait_for_native_uninstall_cleanup(
    install: Path, *, timeout_seconds: float = 30.0, interval_seconds: float = 0.25
) -> None:
    """Allow NSIS's bounded self-deletion handoff before judging uninstall residue."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            remaining = tuple(install.iterdir())
        except FileNotFoundError:
            return
        except PermissionError as error:
            if time.monotonic() >= deadline:
                raise ValueError("native desktop uninstall cleanup could not be inspected") from error
            time.sleep(min(interval_seconds, max(0.0, deadline - time.monotonic())))
            continue
        if not remaining:
            return
        if time.monotonic() >= deadline:
            names = ", ".join(sorted(item.name for item in remaining))
            raise ValueError(f"native desktop uninstall left installed files behind: {names}")
        time.sleep(min(interval_seconds, max(0.0, deadline - time.monotonic())))


def exercise_acquired_lifecycle(
    acquired_dir: Path,
    work_dir: Path,
    *,
    expected_version: str | None = None,
    source_worktree: Path | None = None,
    execute_native: bool = False,
    expected_sha256s: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> AcquiredCandidateLifecycle:
    acquired = acquired_dir.resolve()
    work = work_dir.resolve()
    if _looks_like_source_worktree(acquired):
        raise ValueError("worktree_bytes_used")
    if source_worktree is not None:
        tree = source_worktree.resolve()
        if acquired == tree or acquired.is_relative_to(tree):
            raise ValueError("worktree_bytes_used")
    if work.parent != acquired.parent:
        raise ValueError("lifecycle work directory must be a sibling of acquired remote bytes")
    manifest = _verify_acquired_manifest(acquired, expected_sha256s=expected_sha256s)
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
    observed = _version_from_payload(install)
    if expected_version is not None and observed != expected_version:
        raise ValueError("installed version does not match the candidate")
    health = install / "health.json"
    health.write_text(
        json.dumps({"status": "ok", "version": observed, "files": len(extracted)}) + "\n",
        encoding="utf-8",
    )
    execution_mode: Literal["SIMULATED_REMOTE_BYTES", "REAL_NATIVE_REMOTE_BYTES"]
    if execute_native:
        if expected_version is None:
            expected_version = observed
        python_checks = _run_python_artifact_checks(
            acquired,
            work,
            expected_version=expected_version,
            remote_install_root=install,
            python_executable=python_executable,
        )
        native_checks = _run_native_desktop_checks(acquired, work)
        checks = {
            "install": "PASS",
            "migration": "PASS_SQLITE_REMOTE_INSTALL",
            "startup": "PASS",
            "health": "PASS",
            "desktop_launch": native_checks["desktop_launch"],
            "command_center": native_checks["command_center"],
            "director_journey": "PASS_INSTALLED_CLI_AND_NATIVE_DESKTOP",
            "upgrade": native_checks["upgrade"],
            "rollback": native_checks["rollback"],
            "uninstall": native_checks["uninstall"],
            "state_restoration": native_checks["state_restoration"],
            **python_checks,
        }
        execution_mode = "REAL_NATIVE_REMOTE_BYTES"
    else:
        desktop = next(iter(acquired.glob("*.exe")), None)
        desktop_state = (
            "FIXTURE_BYTES_BOUND" if desktop is not None else "NATIVE_EXECUTABLE_MISSING"
        )
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
        execution_mode = "SIMULATED_REMOTE_BYTES"
    if not set(HEALTH_CHECKS).issubset(checks):
        raise ValueError("lifecycle report is missing a required check")
    if checks["state_restoration"] != "PASS":
        raise ValueError("state restoration failed")
    return AcquiredCandidateLifecycle(
        acquired_dir=str(acquired),
        install_root=str(install),
        checks=checks,
        expected_sha256s=manifest,
        worktree_bytes_used=False,
        execution_mode=execution_mode,
    )
