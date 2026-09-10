"""Windows Job Object / nested-pool enforcement, or explicit unsupported rejection."""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable
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
JobObjectCpuRateControlInformation = 15
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_JOB_TIME = 0x4
JOB_OBJECT_LIMIT_PROCESS_TIME = 0x2
JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1
JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4
CREATE_SUSPENDED = 0x00000004


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


class JobObjectCpuRateControlInformationStruct(ctypes.Structure if ctypes is not None else object):  # type: ignore[misc]
    if ctypes is not None:
        _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


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


def limits_for_adapter(
    *,
    adapter: Any,
    cpu_ceiling: int,
    memory_mb_ceiling: int,
    deadline_seconds: int,
) -> dict[str, Any]:
    """Job Objects are for local Windows processes. Remote adapters get nested pools only."""

    if bool(getattr(adapter, "remote_host", False)):
        if cpu_ceiling < 1 or memory_mb_ceiling < 1 or deadline_seconds < 1:
            raise ResourceLimitError("invalid_limits")
        return {
            "ok": False,
            "mechanism": "remote_worker_job_object_required",
            "handle": None,
            "env": nested_pool_env(cpu_ceiling),
            "deadline_seconds": deadline_seconds,
            "reason": "controller_job_object_not_remote_enforcement",
        }
    if _windows_available():
        return enforce_or_reject(
            cpu_ceiling=cpu_ceiling,
            memory_mb_ceiling=memory_mb_ceiling,
            deadline_seconds=deadline_seconds,
        )
    if cpu_ceiling < 1 or memory_mb_ceiling < 1 or deadline_seconds < 1:
        raise ResourceLimitError("invalid_limits")
    return {
        "ok": True,
        "mechanism": "nested_pool_env_non_windows",
        "handle": None,
        "env": nested_pool_env(cpu_ceiling),
        "deadline_seconds": deadline_seconds,
    }


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
        | JOB_OBJECT_LIMIT_JOB_MEMORY
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_JOB_TIME
        | JOB_OBJECT_LIMIT_PROCESS_TIME
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
    nproc = max(1, int(os.cpu_count() or 1))
    cpu_rate = min(10000, max(1, int((10000 * int(cpu_ceiling)) / nproc)))
    cpu_info = JobObjectCpuRateControlInformationStruct()
    cpu_info.ControlFlags = (
        JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    )
    cpu_info.CpuRate = cpu_rate
    cpu_ok = kernel32.SetInformationJobObject(
        handle,
        JobObjectCpuRateControlInformation,
        ctypes.byref(cpu_info),
        ctypes.sizeof(cpu_info),
    )
    if not cpu_ok:
        kernel32.CloseHandle(handle)
        raise ResourceLimitError("unsupported_limits:job_object_cpu_rate_failed")
    return {
        "ok": True,
        "mechanism": "windows_job_object",
        "handle": int(handle),
        "env": env,
        "process_limit": process_limit,
        "deadline_seconds": deadline_seconds,
        "cpu_rate": cpu_rate,
    }


def close_job_handle(handle: int | None) -> None:
    if not handle or not _windows_available():
        return
    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def _resume_suspended_process(process_handle: int) -> bool:
    """Resume a CREATE_SUSPENDED child after Job Object assignment."""

    if not _windows_available() or process_handle <= 0:
        return False
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    return int(ntdll.NtResumeProcess(process_handle)) == 0


def process_creation_filetime(pid: int) -> str | None:
    """Return the process creation FILETIME as a decimal string, or None."""

    if not _windows_available() or pid <= 0:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    ok = kernel32.GetProcessTimes(
        handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel),
        ctypes.byref(user),
    )
    kernel32.CloseHandle(handle)
    if not ok:
        return None
    value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    return str(value)


def _drain_bounded(
    stream: Any,
    *,
    max_bytes: int,
    overflow: dict[str, bool],
    key: str,
    terminate: Callable[[], None],
) -> str:
    chunks: list[bytes] = []
    total = 0
    while True:
        data = stream.read(4096)
        if not data:
            break
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        if total + len(data) > max_bytes:
            overflow[key] = True
            remain = max(0, max_bytes - total)
            if remain:
                chunks.append(data[:remain])
            terminate()
            break
        chunks.append(data)
        total += len(data)
    return b"".join(chunks).decode("utf-8", errors="replace")


def assign_and_wait(
    *,
    command: list[str],
    working_directory: Path,
    timeout_seconds: int,
    env: dict[str, str],
    handle: int,
    on_started: Callable[[int, str | None], None] | None = None,
    max_output_bytes: int = 65536,
) -> subprocess.CompletedProcess[str]:
    """Assign the child to the Job Object and wait; terminate the job on timeout."""

    if not _windows_available():
        raise ResourceLimitError("unsupported_limits:job_object_unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    # CREATE_SUSPENDED: AssignProcessToJobObject must win before a fast-exit child.
    process = subprocess.Popen(
        command,
        cwd=str(working_directory),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        shell=False,
        creationflags=CREATE_SUSPENDED,
    )
    process_handle = int(process._handle)  # type: ignore[attr-defined]
    creation = process_creation_filetime(int(process.pid))
    assigned = kernel32.AssignProcessToJobObject(handle, process_handle)
    if not assigned:
        process.kill()
        close_job_handle(handle)
        raise ResourceLimitError("unsupported_limits:job_object_assign_failed")
    if not _resume_suspended_process(process_handle):
        process.kill()
        close_job_handle(handle)
        raise ResourceLimitError("unsupported_limits:job_object_resume_failed")
    if on_started is not None:
        on_started(int(process.pid), creation)
    overflow = {"stdout": False, "stderr": False}

    def _terminate_overflow() -> None:
        kernel32.TerminateJobObject(handle, 125)

    stdout_holder: dict[str, str] = {"text": ""}
    stderr_holder: dict[str, str] = {"text": ""}

    def _stdout() -> None:
        stdout_holder["text"] = _drain_bounded(
            process.stdout,
            max_bytes=max_output_bytes,
            overflow=overflow,
            key="stdout",
            terminate=_terminate_overflow,
        )

    def _stderr() -> None:
        stderr_holder["text"] = _drain_bounded(
            process.stderr,
            max_bytes=max_output_bytes,
            overflow=overflow,
            key="stderr",
            terminate=_terminate_overflow,
        )

    reader_out = threading.Thread(target=_stdout, daemon=True)
    reader_err = threading.Thread(target=_stderr, daemon=True)
    reader_out.start()
    reader_err.start()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        kernel32.TerminateJobObject(handle, 124)
        reader_out.join(timeout=5)
        reader_err.join(timeout=5)
        raise subprocess.TimeoutExpired(
            command,
            timeout_seconds,
            output=stdout_holder["text"],
            stderr=stderr_holder["text"],
        ) from None
    reader_out.join(timeout=5)
    reader_err.join(timeout=5)
    completed = subprocess.CompletedProcess(
        command, process.returncode, stdout_holder["text"], stderr_holder["text"]
    )
    completed.pid = process.pid  # type: ignore[attr-defined]
    completed.creation_time = creation  # type: ignore[attr-defined]
    completed.output_truncated = overflow["stdout"] or overflow["stderr"]  # type: ignore[attr-defined]
    if overflow["stdout"] or overflow["stderr"]:
        completed.returncode = completed.returncode or 125
    return completed
