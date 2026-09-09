"""Windows Job Object / nested-pool enforcement, or explicit unsupported rejection."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

try:
    import ctypes
    from ctypes import wintypes
except ImportError:  # pragma: no cover
    ctypes = None  # type: ignore[assignment]
    wintypes = None  # type: ignore[assignment]


class ResourceLimitError(ValueError):
    """Raised when requested limits cannot be enforced on this host."""


JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_JOB_TIME = 0x4
JOB_OBJECT_LIMIT_PROCESS_TIME = 0x2


class LargeInteger(ctypes.Structure if ctypes is not None else object):  # type: ignore[misc]
    if ctypes is not None:
        _fields_ = [("QuadPart", ctypes.c_longlong)]


class JobObjectBasicLimitInformation(ctypes.Structure if ctypes is not None else object):  # type: ignore[misc]
    if ctypes is not None:
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]


class IoCounters(ctypes.Structure if ctypes is not None else object):  # type: ignore[misc]
    if ctypes is not None:
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]


class JobObjectExtendedLimitInformationStruct(ctypes.Structure if ctypes is not None else object):  # type: ignore[misc]
    if ctypes is not None:
        _fields_ = [
            ("BasicLimitInformation", JobObjectBasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


NESTED_POOL_KEYS = frozenset(
    {
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    }
)


def nested_pool_env(cpu_ceiling: int) -> dict[str, str]:
    threads = str(max(1, int(cpu_ceiling)))
    return {key: threads for key in NESTED_POOL_KEYS}


def _windows_available() -> bool:
    return os.name == "nt" and ctypes is not None


def enforce_or_reject(
    *,
    cpu_ceiling: int,
    memory_mb_ceiling: int,
    deadline_seconds: int,
    process_limit: int = 8,
) -> dict[str, Any]:
    """Apply Job Object limits when available; otherwise reject the job."""

    if cpu_ceiling < 1 or memory_mb_ceiling < 1 or deadline_seconds < 1:
        raise ResourceLimitError("invalid_limits")
    env = nested_pool_env(cpu_ceiling)
    if not _windows_available():
        raise ResourceLimitError("unsupported_limits:job_object_unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ResourceLimitError("unsupported_limits:job_object_create_failed")
    info = JobObjectExtendedLimitInformationStruct()
    memory_bytes = int(memory_mb_ceiling) * 1024 * 1024
    hundred_ns = max(1, int(deadline_seconds) * 10_000_000)
    info.BasicLimitInformation.PerProcessUserTimeLimit = hundred_ns
    info.BasicLimitInformation.PerJobUserTimeLimit = hundred_ns
    info.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    info.BasicLimitInformation.ActiveProcessLimit = int(process_limit)
    info.ProcessMemoryLimit = memory_bytes
    info.JobMemoryLimit = memory_bytes
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    ok = kernel32.SetInformationJobObject(
        handle,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        kernel32.CloseHandle(handle)
        raise ResourceLimitError("unsupported_limits:job_object_set_failed")
    return {
        "ok": True,
        "mechanism": "windows_job_object",
        "handle": int(handle),
        "env": env,
        "process_limit": process_limit,
        "deadline_seconds": deadline_seconds,
    }


def close_job_handle(handle: int | None) -> None:
    if not handle or not _windows_available():
        return
    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def assign_and_wait(
    *,
    command: list[str],
    working_directory: Path,
    timeout_seconds: int,
    env: dict[str, str],
    handle: int,
) -> subprocess.CompletedProcess[str]:
    """Assign the child to the Job Object and wait; terminate the job on timeout."""

    if not _windows_available():
        raise ResourceLimitError("unsupported_limits:job_object_unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    process = subprocess.Popen(
        command,
        cwd=str(working_directory),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        shell=False,
    )
    assigned = kernel32.AssignProcessToJobObject(handle, int(process._handle))  # type: ignore[attr-defined]
    if not assigned:
        process.kill()
        close_job_handle(handle)
        raise ResourceLimitError("unsupported_limits:job_object_assign_failed")
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        completed.pid = process.pid  # type: ignore[attr-defined]
        return completed
    except subprocess.TimeoutExpired:
        kernel32.TerminateJobObject(handle, 124)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout_seconds, output=stdout, stderr=stderr)
