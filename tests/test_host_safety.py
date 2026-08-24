from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_pipeline.resilience.host_safety import evaluate_local_host_safety


def _query(*, volumes: list[dict[str, object]], events: list[dict[str, object]]):
    def run(script: str) -> str:
        if "Get-Volume" in script:
            return json.dumps({"volumes": volumes})
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
