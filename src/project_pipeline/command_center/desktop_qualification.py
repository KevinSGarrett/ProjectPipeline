from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import Any

from project_pipeline.command_center.desktop_reproducibility import (
    load_nondeterminism_schema,
    normalize_artifact,
)
from project_pipeline.command_center.desktop_session import current_os_identity, scan_secret_residue

DEFAULT_SERVICE_PORT = 8765
NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR = "NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR"


def _which(name: str) -> str | None:
    return shutil.which(name)


def observe_desktop_toolchain() -> dict[str, Any]:
    rustc = _which("rustc")
    cargo = _which("cargo")
    npm = _which("npm")
    node = _which("node")
    rustc_version = _run_version(rustc)
    cargo_version = _run_version(cargo)
    node_version = _run_version(node)
    npm_version = _run_version(npm, ["--version"])
    return {
        "os": os.name,
        "platform": sys.platform,
        "os_identity_present": bool(current_os_identity()),
        "rustc_path": rustc,
        "cargo_path": cargo,
        "node_path": node,
        "npm_path": npm,
        "rustc_version": rustc_version,
        "cargo_version": cargo_version,
        "node_version": node_version,
        "npm_version": npm_version,
        "webview2_hint": os.environ.get("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER") or "system-default",
    }


def _run_version(executable: str | None, args: list[str] | None = None) -> str | None:
    if not executable:
        return None
    command = [executable, *(args or ["--version"])]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else None


def classify_desktop_artifact(path: Path) -> str | None:
    """Classify a staged PE, MSI, or NSIS file without depending on walk order."""

    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    name = path.name.lower()
    parent = path.parent.name.lower()
    if suffix == ".msi":
        return "msi"
    if suffix != ".exe":
        return None
    if "uninstall" in name:
        return None
    if parent in {"identity", "nsis"} or "setup" in name:
        return "nsis"
    return "executable"


def discover_desktop_artifacts(root: Path, *, hosted_dir: Path | None = None) -> dict[str, Path]:
    found: dict[str, Path] = {}
    local_kinds = (
        ("executable", root / "apps/desktop_shell/src-tauri/target/release", "*.exe"),
        ("msi", root / "apps/desktop_shell/src-tauri/target/release/bundle/msi", "*.msi"),
        ("nsis", root / "apps/desktop_shell/src-tauri/target/release/bundle/nsis", "*.exe"),
    )
    for kind, directory, pattern in local_kinds:
        for path in directory.glob(pattern):
            classified = classify_desktop_artifact(path)
            if classified == kind:
                found[kind] = path
                break
    hosted_dirs = [
        hosted_dir,
        root / "evidence/desktop/hosted_artifacts",
    ]
    for hosted in hosted_dirs:
        if hosted is None or not hosted.is_dir():
            continue
        for path in hosted.rglob("*"):
            classified = classify_desktop_artifact(path)
            if classified is not None:
                found[classified] = path
    return found


def bind_artifact_identities(root: Path, artifacts: dict[str, Path]) -> dict[str, Any]:
    schema = load_nondeterminism_schema(root)
    identities: dict[str, Any] = {}
    for kind, path in artifacts.items():
        normalized = normalize_artifact(path, schema)
        identities[kind] = {
            "path": path.as_posix(),
            "raw_sha256": normalized.raw_sha256,
            "normalized_sha256": normalized.normalized_sha256,
            "removed_fields": list(normalized.removed_fields),
        }
    return identities


def probe_loopback_service(port: int = DEFAULT_SERVICE_PORT, timeout_s: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_s):
            return True
    except OSError:
        return False


def launch_native_process(
    executable: Path,
    *,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    wait_window_s: float = 20.0,
    terminate: bool = True,
) -> dict[str, Any]:
    if os.name != "nt":
        return {
            "launched": False,
            "reason": "NOT_WINDOWS",
            "pid": None,
        }
    if not executable.is_file():
        return {"launched": False, "reason": "EXECUTABLE_MISSING", "pid": None}
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        [str(executable), *(extra_args or [])],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    window: str | None = None
    deadline = time.time() + wait_window_s
    while time.time() < deadline and process.poll() is None:
        window = _find_window_for_pid(process.pid)
        if window:
            break
        time.sleep(0.25)
    running = process.poll() is None
    handshake = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / (
        f"pp-cc-handshake-{process.pid}.json"
    )
    if terminate and running:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
    return {
        "launched": running or bool(window),
        "reason": "PROCESS_STARTED" if running or window else "PROCESS_EXITED",
        "pid": process.pid,
        "native_window_observed": bool(window),
        "window_title": window,
        "handshake_path": str(handshake),
        "handshake_present": handshake.is_file(),
        "terminated": terminate,
    }


def _find_window_for_pid(pid: int) -> str | None:
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    found: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:  # type: ignore[untyped-decorator]
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        found.append(buffer.value)
        return False

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def resolve_predecessor_release(root: Path) -> dict[str, Any]:
    marker = root / "evidence/desktop/predecessor_release.json"
    if marker.is_file():
        payload = json.loads(marker.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("tag") and payload.get("asset_sha256"):
            return payload
    return {
        "status": NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR,
        "reason": "no governed predecessor desktop release is recorded for upgrade credit",
    }


def _installer_sequence(upgrade_applicable: bool) -> list[str]:
    if upgrade_applicable:
        return [
            "predecessor_install",
            "candidate_upgrade",
            "rollback",
            "candidate_reinstall",
            "uninstall",
        ]
    return ["clean_install", "repair", "rollback", "uninstall"]


def _run_installer_command(
    command: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    execute = runner or subprocess.run
    try:
        completed = execute(
            command,
            check=False,
            capture_output=True,
            timeout=timeout_s,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "ok": False,
            "command": command,
            "reason": error.__class__.__name__,
        }
    stdout = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": command,
        "stdout_tail": stdout[-400:],
        "stderr_tail": stderr[-400:],
    }


_MSI_ALREADY_REMOVED_CODES = frozenset({1605, 1614})


def _run_uninstall_step(
    *,
    name: str,
    kind: str,
    uninstall_cmd: list[str],
    uninstaller: Path | None,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] | None,
    required: bool,
) -> dict[str, Any]:
    missing = kind == "nsis" and uninstaller is not None and not uninstaller.is_file()
    if missing and not required:
        return {
            "name": name,
            "ok": True,
            "reason": "ALREADY_REMOVED",
            "command": uninstall_cmd,
        }
    if missing and runner is None:
        return {
            "name": name,
            "ok": False,
            "reason": "UNINSTALLER_MISSING",
            "command": uninstall_cmd,
        }
    result = _run_installer_command(uninstall_cmd, runner=runner)
    if result["ok"]:
        return {"name": name, **result}
    if required:
        return {"name": name, **result}
    already_removed = (
        missing
        or result.get("reason") in {"FileNotFoundError", "OSError"}
        or (kind == "msi" and result.get("returncode") in _MSI_ALREADY_REMOVED_CODES)
    )
    if already_removed:
        return {"name": name, **result, "ok": True, "reason": "ALREADY_REMOVED"}
    return {"name": name, **result}


def _remaining_files(target_root: Path) -> list[str]:
    if not target_root.exists():
        return []
    return sorted(
        path.relative_to(target_root).as_posix()
        for path in target_root.rglob("*")
        if path.is_file()
    )


def execute_installer_lifecycle(
    *,
    artifacts: dict[str, Path],
    predecessor: dict[str, Any],
    target_root: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    forbidden_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    installer = artifacts.get("nsis") or artifacts.get("msi")
    upgrade_applicable = predecessor.get("status") != NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR
    sequence = _installer_sequence(upgrade_applicable)
    if installer is None:
        return {
            "executed": False,
            "upgrade_credit": False,
            "predecessor": predecessor,
            "reason": "INSTALLER_ARTIFACT_MISSING",
            "planned_sequence": sequence,
        }
    if upgrade_applicable:
        return {
            "executed": False,
            "upgrade_credit": False,
            "predecessor": predecessor,
            "installer_path": installer.as_posix(),
            "reason": "PREDECESSOR_BYTES_NOT_STAGED",
            "planned_sequence": sequence,
        }
    target_root.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    kind = "nsis" if installer.suffix.lower() == ".exe" else "msi"
    if kind == "nsis":
        install_cmd = [str(installer), "/S", f"/D={target_root}"]
        uninstaller = target_root / "uninstall.exe"
        uninstall_cmd = [str(uninstaller), "/S"]
    else:
        install_cmd = [
            "msiexec",
            "/i",
            str(installer),
            "/qn",
            "/norestart",
            f"INSTALLDIR={target_root}",
        ]
        uninstall_cmd = ["msiexec", "/x", str(installer), "/qn", "/norestart"]

    steps.append({"name": "clean_install", **_run_installer_command(install_cmd, runner=runner)})
    steps.append({"name": "repair", **_run_installer_command(install_cmd, runner=runner)})
    nsis_uninstaller = uninstaller if kind == "nsis" else None
    steps.append(
        _run_uninstall_step(
            name="rollback",
            kind=kind,
            uninstall_cmd=uninstall_cmd,
            uninstaller=nsis_uninstaller,
            runner=runner,
            required=True,
        )
    )
    steps.append(
        _run_uninstall_step(
            name="uninstall",
            kind=kind,
            uninstall_cmd=uninstall_cmd,
            uninstaller=nsis_uninstaller,
            runner=runner,
            required=False,
        )
    )
    remaining = _remaining_files(target_root)
    residue = scan_secret_residue(
        [path for path in target_root.rglob("*") if path.is_file()] if target_root.exists() else [],
        forbidden_values=forbidden_values,
    )
    executed = all(step.get("ok") for step in steps)
    return {
        "executed": executed,
        "upgrade_credit": False,
        "predecessor": predecessor,
        "installer_path": installer.as_posix(),
        "installer_kind": kind,
        "target_root": target_root.as_posix(),
        "planned_sequence": sequence,
        "steps": steps,
        "remaining_files": remaining,
        "secret_residue": residue,
        "reason": "INSTALLER_LIFECYCLE_EXECUTED" if executed else "INSTALLER_LIFECYCLE_FAILED",
        "clean_removal": remaining == [] and residue == [],
    }


def evaluate_installer_lifecycle(
    *,
    artifacts: dict[str, Path],
    predecessor: dict[str, Any],
    execute: bool = False,
    target_root: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    forbidden_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    installer = artifacts.get("nsis") or artifacts.get("msi")
    upgrade_applicable = predecessor.get("status") != NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR
    sequence = _installer_sequence(upgrade_applicable)
    if execute:
        if target_root is None:
            raise ValueError("installer execution requires target_root")
        return execute_installer_lifecycle(
            artifacts=artifacts,
            predecessor=predecessor,
            target_root=target_root,
            runner=runner,
            forbidden_values=forbidden_values,
        )
    if installer is None:
        return {
            "executed": False,
            "upgrade_credit": False,
            "predecessor": predecessor,
            "reason": "INSTALLER_ARTIFACT_MISSING",
            "planned_sequence": sequence,
        }
    return {
        "executed": False,
        "installer_path": installer.as_posix(),
        "upgrade_credit": False,
        "predecessor": predecessor,
        "reason": "INSTALLER_LIFECYCLE_PENDING_LOCAL_EXECUTION",
        "planned_sequence": sequence,
    }


def qualify_desktop_slice(
    root: Path,
    *,
    hosted_dir: Path | None = None,
    execute_installer: bool = False,
    installer_target: Path | None = None,
    python_executable: str | None = None,
    wait_window_s: float = 2.0,
) -> dict[str, Any]:
    root = root.resolve()
    toolchain = observe_desktop_toolchain()
    artifacts = discover_desktop_artifacts(root, hosted_dir=hosted_dir)
    identities = bind_artifact_identities(root, artifacts) if artifacts else {}
    service_running = probe_loopback_service()
    extra_env = {
        "PROJECT_PIPELINE_ROOT": str(root),
        "PROJECT_PIPELINE_PYTHON": python_executable or sys.executable,
    }
    launch = (
        launch_native_process(
            artifacts["executable"],
            extra_env=extra_env,
            wait_window_s=wait_window_s,
        )
        if "executable" in artifacts
        else {"launched": False, "reason": "EXECUTABLE_MISSING", "pid": None}
    )
    predecessor = resolve_predecessor_release(root)
    installer = evaluate_installer_lifecycle(
        artifacts=artifacts,
        predecessor=predecessor,
        execute=execute_installer,
        target_root=installer_target,
    )
    result = {
        "schema_version": "1.0.0",
        "toolchain": toolchain,
        "artifacts": {key: value.as_posix() for key, value in artifacts.items()},
        "identities": identities,
        "loopback_service_running": service_running,
        "native_launch": launch,
        "installer_lifecycle": installer,
        "lockfiles": {
            "npm": (root / "apps/command_center/package-lock.json").is_file(),
            "cargo": (root / "apps/desktop_shell/src-tauri/Cargo.lock").is_file(),
        },
        "requirement_ux_0004_closed": False,
    }
    return result
