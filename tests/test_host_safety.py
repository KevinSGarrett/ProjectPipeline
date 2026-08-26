from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_pipeline.resilience.host_safety import (
    _STORAGE_EVENT_QUERY,
    evaluate_local_host_safety,
)


def _query(
    *,
    volumes: list[dict[str, object]],
    events: list[dict[str, object]],
    memory: list[dict[str, object]] | None = None,
):
    default_memory = [
        {
            "TotalVisibleMemorySize": 16 * 1024 * 1024,
            "FreePhysicalMemory": 8 * 1024 * 1024,
            "TotalVirtualMemorySize": 32 * 1024 * 1024,
            "FreeVirtualMemory": 16 * 1024 * 1024,
            "PageFileAllocatedBaseSize": 16 * 1024,
            "PageFileCurrentUsage": 2 * 1024,
            "PageFilePeakUsage": 4 * 1024,
        }
    ]

    def run(script: str) -> str:
        if "Get-Volume" in script:
            return json.dumps({"volumes": volumes})
        if "Win32_OperatingSystem" in script:
            return json.dumps({"memory": default_memory if memory is None else memory})
        return json.dumps({"events": events})

    return run


def test_host_safety_accepts_healthy_windows_host(tmp_path: Path):
    report = evaluate_local_host_safety(
        tmp_path,
        system_name="Windows",
        query=_query(
            volumes=[
                {
                    "DriveLetter": "C",
                    "HealthStatus": "Healthy",
                    "OperationalStatus": "OK",
                    "SizeRemaining": 8 * 1024 * 1024 * 1024,
                }
            ],
            events=[],
        ),
    )

    assert report["state"] == "SAFE"
    assert report["blockers"] == []
    assert report["memory"]["available_physical_bytes"] == 8 * 1024 * 1024 * 1024


def test_host_safety_storage_query_treats_no_matching_events_as_an_empty_set():
    """A clean System log is safe data, not an unavailable host inspection."""

    assert "NoMatchingEventsFound" in _STORAGE_EVENT_QUERY
    assert "@()" in _STORAGE_EVENT_QUERY


def test_host_safety_blocks_unhealthy_volume_and_recent_storage_faults(tmp_path: Path):
    report = evaluate_local_host_safety(
        tmp_path,
        system_name="Windows",
        query=_query(
            volumes=[
                {
                    "DriveLetter": "F",
                    "HealthStatus": "Warning",
                    "OperationalStatus": "Full Repair Needed",
                    "SizeRemaining": 8192,
                }
            ],
            events=[
                {"Id": 129, "ProviderName": "stornvme"},
                {"Id": 1001, "ProviderName": "Microsoft-Windows-WER-SystemErrorReporting"},
            ],
        ),
    )

    assert report["state"] == "BLOCKED"
    assert {item["code"] for item in report["blockers"]} == {
        "volume-unhealthy",
        "volume-critical-free-space",
        "recent-nvme-reset",
        "recent-bugcheck",
    }


def test_host_safety_blocks_when_no_mounted_volumes_are_reported(tmp_path: Path):
    report = evaluate_local_host_safety(
        tmp_path,
        system_name="Windows",
        query=_query(volumes=[], events=[]),
    )

    assert report["state"] == "BLOCKED"
    assert report["blockers"] == [{"code": "mounted-volume-inspection-empty"}]


def test_host_safety_blocks_low_available_physical_memory(tmp_path: Path):
    def query(script: str) -> str:
        if "Get-Volume" in script:
            return json.dumps(
                {
                    "volumes": [
                        {
                            "DriveLetter": "C",
                            "HealthStatus": "Healthy",
                            "OperationalStatus": "OK",
                            "SizeRemaining": 8 * 1024 * 1024 * 1024,
                        }
                    ]
                }
            )
        if "Win32_OperatingSystem" in script:
            return json.dumps(
                {
                    "memory": [
                        {
                            "TotalVisibleMemorySize": 32 * 1024 * 1024,
                            "FreePhysicalMemory": 512 * 1024,
                            "TotalVirtualMemorySize": 64 * 1024 * 1024,
                            "FreeVirtualMemory": 16 * 1024 * 1024,
                            "PageFileAllocatedBaseSize": 32 * 1024,
                            "PageFileCurrentUsage": 8 * 1024,
                            "PageFilePeakUsage": 24 * 1024,
                        }
                    ]
                }
            )
        return json.dumps({"events": []})

    report = evaluate_local_host_safety(tmp_path, system_name="Windows", query=query)

    assert report["state"] == "BLOCKED"
    assert report["blockers"] == [
        {
            "code": "memory-pressure-low-available-physical",
            "available_bytes": 512 * 1024 * 1024,
            "minimum_required_bytes": int(32 * 1024 * 1024 * 1024 * 0.10),
        }
    ]


def test_host_safety_blocks_low_commit_headroom(tmp_path: Path):
    def query(script: str) -> str:
        if "Get-Volume" in script:
            return json.dumps(
                {
                    "volumes": [
                        {
                            "DriveLetter": "C",
                            "HealthStatus": "Healthy",
                            "OperationalStatus": "OK",
                            "SizeRemaining": 8 * 1024 * 1024 * 1024,
                        }
                    ]
                }
            )
        if "Win32_OperatingSystem" in script:
            return json.dumps(
                {
                    "memory": [
                        {
                            "TotalVisibleMemorySize": 16 * 1024 * 1024,
                            "FreePhysicalMemory": 8 * 1024 * 1024,
                            "TotalVirtualMemorySize": 32 * 1024 * 1024,
                            "FreeVirtualMemory": 1024 * 1024,
                            "PageFileAllocatedBaseSize": 16 * 1024,
                            "PageFileCurrentUsage": 15 * 1024,
                            "PageFilePeakUsage": 15 * 1024,
                        }
                    ]
                }
            )
        return json.dumps({"events": []})

    report = evaluate_local_host_safety(tmp_path, system_name="Windows", query=query)

    assert report["state"] == "BLOCKED"
    assert report["blockers"] == [
        {
            "code": "memory-pressure-low-commit-headroom",
            "available_bytes": 1024 * 1024 * 1024,
            "minimum_required_bytes": 2 * 1024 * 1024 * 1024,
        }
    ]


def test_host_safety_blocks_inconsistent_memory_capacity_counters(tmp_path: Path):
    volumes = [
        {
            "DriveLetter": "C",
            "HealthStatus": "Healthy",
            "OperationalStatus": "OK",
            "SizeRemaining": 8 * 1024 * 1024 * 1024,
        }
    ]
    for memory in [
        [
            {
                "TotalVisibleMemorySize": 16 * 1024 * 1024,
                "FreePhysicalMemory": 17 * 1024 * 1024,
                "TotalVirtualMemorySize": 32 * 1024 * 1024,
                "FreeVirtualMemory": 16 * 1024 * 1024,
                "PageFileAllocatedBaseSize": 16 * 1024,
                "PageFileCurrentUsage": 2 * 1024,
                "PageFilePeakUsage": 4 * 1024,
            }
        ],
        [
            {
                "TotalVisibleMemorySize": 16 * 1024 * 1024,
                "FreePhysicalMemory": 8 * 1024 * 1024,
                "TotalVirtualMemorySize": 32 * 1024 * 1024,
                "FreeVirtualMemory": 33 * 1024 * 1024,
                "PageFileAllocatedBaseSize": 16 * 1024,
                "PageFileCurrentUsage": 2 * 1024,
                "PageFilePeakUsage": 4 * 1024,
            }
        ],
    ]:
        report = evaluate_local_host_safety(
            tmp_path,
            system_name="Windows",
            query=_query(volumes=volumes, events=[], memory=memory),
        )
        assert report["state"] == "BLOCKED"
        assert report["blockers"] == [{"code": "memory-inspection-invalid"}]


def test_host_safety_blocks_when_windows_inspection_is_unavailable(tmp_path: Path):
    def unavailable(_script: str) -> str:
        raise OSError("unavailable")

    report = evaluate_local_host_safety(tmp_path, system_name="Windows", query=unavailable)

    assert report["state"] == "BLOCKED"
    assert report["blockers"] == [{"code": "host-safety-inspection-unavailable"}]


def test_host_safety_blocks_when_windows_inspection_times_out(tmp_path: Path):
    def timeout(_script: str) -> str:
        raise subprocess.TimeoutExpired("powershell.exe", 20)

    report = evaluate_local_host_safety(tmp_path, system_name="Windows", query=timeout)

    assert report["state"] == "BLOCKED"
    assert report["blockers"] == [{"code": "host-safety-inspection-unavailable"}]


def test_host_safety_is_not_required_on_non_windows_hosts(tmp_path: Path):
    report = evaluate_local_host_safety(tmp_path, system_name="Linux")

    assert report["state"] == "NOT_APPLICABLE"
