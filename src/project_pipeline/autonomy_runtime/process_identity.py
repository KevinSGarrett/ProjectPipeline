"""Live process identity for campaign fencing. PID existence is not identity."""

from __future__ import annotations

import contextlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.qualification import _pid_alive


def _filetime_to_utc_iso(low: int, high: int) -> str:
    ticks = (int(high) << 32) | int(low)
    unix = ticks / 10_000_000 - 11_644_473_600
    return datetime.fromtimestamp(unix, UTC).isoformat()


def inspect_process(pid: int) -> dict[str, Any] | None:
    if pid <= 0 or not _pid_alive(pid):
        return None
    if os.name == "nt":
        return _inspect_windows(pid)
    return _inspect_posix(pid)


def current_process_identity(*, service_identity: str | None = None) -> dict[str, Any]:
    identity = inspect_process(os.getpid())
    if identity is None:
        identity = {
            "process_id": os.getpid(),
            "executable": str(Path(sys.executable).resolve()),
            "started_at_utc": datetime.now(UTC).isoformat(),
            "alive": True,
        }
    identity["service_identity"] = service_identity
    return identity


def identities_match(bound: dict[str, Any] | None, live: dict[str, Any] | None) -> bool:
    if not bound or not live:
        return False
    if int(bound.get("process_id") or 0) != int(live.get("process_id") or 0):
        return False
    bound_exe = str(bound.get("executable") or "").casefold()
    live_exe = str(live.get("executable") or "").casefold()
    if bound_exe and not live_exe:
        return False
    if (
        bound_exe
        and live_exe
        and Path(bound_exe).name != Path(live_exe).name
        and bound_exe != live_exe
    ):
        return False
    bound_start = str(bound.get("started_at_utc") or "")
    live_start = str(live.get("started_at_utc") or "")
    return not (bound_start and live_start and bound_start != live_start)


def _inspect_windows(pid: int) -> dict[str, Any] | None:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        query = getattr(kernel32, "QueryFullProcessImageNameW", None)
        executable = ""
        if query is not None and query(handle, 0, buffer, ctypes.byref(size)):
            executable = buffer.value
        if not executable:
            executable = str(Path(sys.executable).resolve()) if pid == os.getpid() else ""
        return {
            "process_id": int(pid),
            "executable": executable,
            "started_at_utc": _filetime_to_utc_iso(creation.dwLowDateTime, creation.dwHighDateTime),
            "alive": True,
        }
    finally:
        kernel32.CloseHandle(handle)


def _inspect_posix(pid: int) -> dict[str, Any] | None:
    proc = Path(f"/proc/{pid}")
    if not proc.exists():
        if pid == os.getpid():
            return {
                "process_id": int(pid),
                "executable": str(Path(sys.executable).resolve()),
                "started_at_utc": datetime.now(UTC).isoformat(),
                "alive": True,
            }
        return None
    executable = ""
    exe = proc / "exe"
    try:
        executable = str(exe.resolve())
    except OSError:
        executable = str(Path(sys.executable).resolve()) if pid == os.getpid() else ""
    started = datetime.now(UTC).isoformat()
    with contextlib.suppress(OSError):
        started = datetime.fromtimestamp((proc / "stat").stat().st_ctime, UTC).isoformat()
    return {
        "process_id": int(pid),
        "executable": executable,
        "started_at_utc": started,
        "alive": True,
    }
