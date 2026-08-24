"""Fail-closed Windows host checks before sustained local campaign work."""

from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

_MIN_FREE_BYTES = 1024 * 1024 * 1024
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
$rows = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = $start; Id = @(129, 1001) } |
    Where-Object {
        ($_.Id -eq 129 -and $_.ProviderName -eq 'stornvme') -or
        ($_.Id -eq 1001 -and $_.ProviderName -eq 'Microsoft-Windows-WER-SystemErrorReporting')
    } |
    Select-Object TimeCreated, Id, ProviderName)
[pscustomobject]@{ events = $rows } | ConvertTo-Json -Compress
""".replace("__LOOKBACK_HOURS__", str(_EVENT_LOOKBACK_HOURS))


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
            "recent_nvme_resets": 0,
            "recent_bugchecks": 0,
        }

    try:
        volumes = _query_rows(_VOLUME_QUERY, key="volumes", query=query)
        events = _query_rows(_STORAGE_EVENT_QUERY, key="events", query=query)
    except HostSafetyError as error:
        return {
            "state": "BLOCKED",
            "root": str(root.resolve()),
            "blockers": [{"code": str(error)}],
            "volumes": [],
            "recent_nvme_resets": None,
            "recent_bugchecks": None,
        }

    blockers: list[dict[str, Any]] = []
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
