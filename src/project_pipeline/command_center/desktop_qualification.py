from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

from project_pipeline.command_center.desktop_reproducibility import (
    load_nondeterminism_schema,
    normalize_artifact,
)
from project_pipeline.command_center.desktop_session import current_os_identity

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


def discover_desktop_artifacts(root: Path) -> dict[str, Path]:
    candidates = {
        "executable": list((root / "apps/desktop_shell/src-tauri/target/release").glob("*.exe")),
        "msi": list(
            (root / "apps/desktop_shell/src-tauri/target/release/bundle/msi").glob("*.msi")
        ),
        "nsis": list(
            (root / "apps/desktop_shell/src-tauri/target/release/bundle/nsis").glob("*.exe")
        ),
    }
    found: dict[str, Path] = {}
    for kind, matches in candidates.items():
        if matches:
            found[kind] = matches[0]
    hosted = root / "evidence/desktop/hosted_artifacts"
    if hosted.is_dir():
        for path in hosted.rglob("*"):
            if path.suffix.lower() == ".exe" and "nsis" not in path.as_posix().lower():
                found.setdefault("executable", path)
            elif path.suffix.lower() == ".msi":
                found.setdefault("msi", path)
            elif path.suffix.lower() == ".exe":
                found.setdefault("nsis", path)
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
    executable: Path, *, extra_args: list[str] | None = None
) -> dict[str, Any]:
    if os.name != "nt":
        return {
            "launched": False,
            "reason": "NOT_WINDOWS",
            "pid": None,
        }
    if not executable.is_file():
        return {"launched": False, "reason": "EXECUTABLE_MISSING", "pid": None}
    process = subprocess.Popen(
        [str(executable), *(extra_args or [])],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)
    running = process.poll() is None
    window = _find_window_for_pid(process.pid) if running else None
    if running:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
    return {
        "launched": running,
        "reason": "PROCESS_STARTED" if running else "PROCESS_EXITED",
        "pid": process.pid,
        "native_window_observed": bool(window),
        "window_title": window,
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


def evaluate_installer_lifecycle(
    *,
    artifacts: dict[str, Path],
    predecessor: dict[str, Any],
) -> dict[str, Any]:
    installer = artifacts.get("msi") or artifacts.get("nsis")
    upgrade_applicable = predecessor.get("status") != NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR
    if installer is None:
        return {
            "executed": False,
            "upgrade_credit": False,
            "predecessor": predecessor,
            "reason": "INSTALLER_ARTIFACT_MISSING",
            "planned_sequence": (
                ["clean_install", "repair", "rollback", "uninstall"]
                if not upgrade_applicable
                else [
                    "predecessor_install",
                    "candidate_upgrade",
                    "rollback",
                    "candidate_reinstall",
                    "uninstall",
                ]
            ),
        }
    return {
        "executed": False,
        "installer_path": installer.as_posix(),
        "upgrade_credit": False,
        "predecessor": predecessor,
        "reason": "INSTALLER_LIFECYCLE_PENDING_LOCAL_EXECUTION",
        "planned_sequence": (
            ["clean_install", "repair", "rollback", "uninstall"]
            if not upgrade_applicable
            else [
                "predecessor_install",
                "candidate_upgrade",
                "rollback",
                "candidate_reinstall",
                "uninstall",
            ]
        ),
    }


def qualify_desktop_slice(root: Path) -> dict[str, Any]:
    root = root.resolve()
    toolchain = observe_desktop_toolchain()
    artifacts = discover_desktop_artifacts(root)
    identities = bind_artifact_identities(root, artifacts) if artifacts else {}
    service_running = probe_loopback_service()
    launch = (
        launch_native_process(artifacts["executable"])
        if "executable" in artifacts
        else {"launched": False, "reason": "EXECUTABLE_MISSING", "pid": None}
    )
    predecessor = resolve_predecessor_release(root)
    installer = evaluate_installer_lifecycle(artifacts=artifacts, predecessor=predecessor)
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
