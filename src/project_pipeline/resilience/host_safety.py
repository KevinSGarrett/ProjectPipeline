"""Fail-closed Windows host checks before sustained local campaign work."""

from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

_MIN_FREE_BYTES = 1024 * 1024 * 1024
_MIN_AVAILABLE_MEMORY_BYTES = 2 * 1024 * 1024 * 1024
_MIN_AVAILABLE_MEMORY_FRACTION = 0.10
_EVENT_LOOKBACK_HOURS = 72

_VOLUME_QUERY = r"""
$ErrorActionPreference = 'Stop'
$rows = @(Get-Volume | Where-Object { $null -ne $_.DriveLetter } |
    Select-Object DriveLetter, HealthStatus, OperationalStatus, SizeRemaining, Size)
[pscustomobject]@{ volumes = $rows } | ConvertTo-Json -Compress
"""

_STORAGE_EVENT_QUERY = r"""
$ErrorActionPreference = 'Stop'
$start = (Get-Date).AddHours(-__LOOKBACK_HOURS__)
$events = @(
    try {
        Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = $start; Id = @(129, 1001) } -ErrorAction Stop
    }
    catch {
        if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound,*') {
            @()
        }
        else {
            throw
        }
    }
)
$rows = @($events |
    Where-Object {
        ($_.Id -eq 129 -and $_.ProviderName -eq 'stornvme') -or
        ($_.Id -eq 1001 -and $_.ProviderName -eq 'Microsoft-Windows-WER-SystemErrorReporting')
    } |
    Select-Object TimeCreated, Id, ProviderName)
[pscustomobject]@{ events = $rows } | ConvertTo-Json -Compress
""".replace("__LOOKBACK_HOURS__", str(_EVENT_LOOKBACK_HOURS))

_MEMORY_QUERY = r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$pageFiles = @(Get-CimInstance Win32_PageFileUsage)
$row = [pscustomobject]@{
    TotalVisibleMemorySize = $os.TotalVisibleMemorySize
    FreePhysicalMemory = $os.FreePhysicalMemory
    TotalVirtualMemorySize = $os.TotalVirtualMemorySize
    FreeVirtualMemory = $os.FreeVirtualMemory
    PageFileAllocatedBaseSize = [int64](($pageFiles | Measure-Object -Property AllocatedBaseSize -Sum).Sum)
    PageFileCurrentUsage = [int64](($pageFiles | Measure-Object -Property CurrentUsage -Sum).Sum)
    PageFilePeakUsage = [int64](($pageFiles | Measure-Object -Property PeakUsage -Sum).Sum)
}
[pscustomobject]@{ memory = @($row) } | ConvertTo-Json -Compress
"""


class HostSafetyError(RuntimeError):
    """Raised when local campaign work would run on an unsafe Windows host."""


WindowsQuery = Callable[[str], str]


def _default_windows_query(script: str) -> str:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise OSError("windows-host-query-failed")
    return completed.stdout


def _object_list(value: Any, *, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("windows-host-query-malformed")
    raw = value.get(key, [])
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError("windows-host-query-malformed")
    return raw


def _query_rows(script: str, *, key: str, query: WindowsQuery) -> list[dict[str, Any]]:
    try:
        return _object_list(json.loads(query(script)), key=key)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
        raise HostSafetyError("host-safety-inspection-unavailable") from error


def _memory_value(row: dict[str, Any], key: str) -> int:
    """Return one non-negative Windows memory counter without accepting malformed data."""

    try:
        value = int(row[key])
    except (KeyError, TypeError, ValueError) as error:
        raise HostSafetyError("memory-inspection-invalid") from error
    if value < 0:
        raise HostSafetyError("memory-inspection-invalid")
    return value


def _memory_report(rows: list[dict[str, Any]]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Normalize memory capacity and return fail-closed pressure findings.

    WMI reports operating-system counters in kibibytes and page-file counters in
    mebibytes.  The report uses bytes so campaign evidence remains unambiguous.
    """

    if len(rows) != 1:
        raise HostSafetyError("memory-inspection-empty")
    row = rows[0]
    total_physical = _memory_value(row, "TotalVisibleMemorySize") * 1024
    available_physical = _memory_value(row, "FreePhysicalMemory") * 1024
    total_virtual = _memory_value(row, "TotalVirtualMemorySize") * 1024
    available_virtual = _memory_value(row, "FreeVirtualMemory") * 1024
    if (
        total_physical <= 0
        or total_virtual <= 0
        or available_physical > total_physical
        or available_virtual > total_virtual
    ):
        raise HostSafetyError("memory-inspection-invalid")
    minimum_available = max(
        _MIN_AVAILABLE_MEMORY_BYTES,
        int(total_physical * _MIN_AVAILABLE_MEMORY_FRACTION),
    )
    memory = {
        "total_physical_bytes": total_physical,
        "available_physical_bytes": available_physical,
        "total_virtual_bytes": total_virtual,
        "available_virtual_bytes": available_virtual,
        "minimum_available_bytes": minimum_available,
        "pagefile_allocated_bytes": _memory_value(row, "PageFileAllocatedBaseSize") * 1024 * 1024,
        "pagefile_current_usage_bytes": _memory_value(row, "PageFileCurrentUsage") * 1024 * 1024,
        "pagefile_peak_usage_bytes": _memory_value(row, "PageFilePeakUsage") * 1024 * 1024,
    }
    blockers: list[dict[str, Any]] = []
    if available_physical < minimum_available:
        blockers.append(
            {
                "code": "memory-pressure-low-available-physical",
                "available_bytes": available_physical,
                "minimum_required_bytes": minimum_available,
            }
        )
    if available_virtual < minimum_available:
        blockers.append(
            {
                "code": "memory-pressure-low-commit-headroom",
                "available_bytes": available_virtual,
                "minimum_required_bytes": minimum_available,
            }
        )
    return memory, blockers


def evaluate_local_host_safety(
    root: Path,
    *,
    system_name: str | None = None,
    query: WindowsQuery = _default_windows_query,
) -> dict[str, Any]:
    """Return a compact host safety report without modifying the operating system."""

    operating_system = system_name or platform.system()
    if operating_system.lower() != "windows":
        return {
            "state": "NOT_APPLICABLE",
            "root": str(root.resolve()),
            "blockers": [],
            "volumes": [],
            "memory": None,
            "recent_nvme_resets": 0,
            "recent_bugchecks": 0,
        }

    try:
        volumes = _query_rows(_VOLUME_QUERY, key="volumes", query=query)
        events = _query_rows(_STORAGE_EVENT_QUERY, key="events", query=query)
        memory_rows = _query_rows(_MEMORY_QUERY, key="memory", query=query)
        memory, memory_blockers = _memory_report(memory_rows)
    except HostSafetyError as error:
        return {
            "state": "BLOCKED",
            "root": str(root.resolve()),
            "blockers": [{"code": str(error)}],
            "volumes": [],
            "memory": None,
            "recent_nvme_resets": None,
            "recent_bugchecks": None,
        }

    blockers: list[dict[str, Any]] = []
    blockers.extend(memory_blockers)
    normalized_volumes: list[dict[str, Any]] = []
    if not volumes:
        blockers.append({"code": "mounted-volume-inspection-empty"})
    for volume in volumes:
        drive = str(volume.get("DriveLetter") or "").upper()
        health = str(volume.get("HealthStatus") or "Unknown")
        operational = str(volume.get("OperationalStatus") or "Unknown")
        try:
            remaining = int(volume.get("SizeRemaining") or 0)
        except (TypeError, ValueError):
            remaining = 0
        normalized_volumes.append(
            {
                "drive": drive,
                "health": health,
                "operational": operational,
                "size_remaining": remaining,
            }
        )
        if health.lower() != "healthy" or operational.lower() != "ok":
            blockers.append({"code": "volume-unhealthy", "drive": drive})
        if remaining < _MIN_FREE_BYTES:
            blockers.append({"code": "volume-critical-free-space", "drive": drive})

    nvme_resets = sum(
        1
        for event in events
        if int(event.get("Id") or 0) == 129 and str(event.get("ProviderName") or "") == "stornvme"
    )
    bugchecks = sum(
        1
        for event in events
        if int(event.get("Id") or 0) == 1001
        and str(event.get("ProviderName") or "") == "Microsoft-Windows-WER-SystemErrorReporting"
    )
    if nvme_resets:
        blockers.append({"code": "recent-nvme-reset", "count": nvme_resets})
    if bugchecks:
        blockers.append({"code": "recent-bugcheck", "count": bugchecks})
    return {
        "state": "SAFE" if not blockers else "BLOCKED",
        "root": str(root.resolve()),
        "blockers": blockers,
        "volumes": normalized_volumes,
        "memory": memory,
        "recent_nvme_resets": nvme_resets,
        "recent_bugchecks": bugchecks,
    }


def require_safe_local_host(root: Path) -> dict[str, Any]:
    """Fail closed before a campaign starts high-I/O work on a risky host."""

    report = evaluate_local_host_safety(root)
    if report["state"] == "BLOCKED":
        codes = ",".join(str(item["code"]) for item in report["blockers"])
        raise HostSafetyError(f"host-safety-blocked:{codes}")
    return report
