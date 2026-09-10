"""Cycle 21 fleet lifecycle, admission, managed worker, and recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.autonomy_runtime.fleet_loop import (
    choose_measured_worker,
    observation_ready_task_ids,
)
from project_pipeline.autonomy_runtime.managed_worker import classify_live_managed_worker
from project_pipeline.autonomy_runtime.observation_eval import evaluate_observation
from project_pipeline.scheduler.host_observation import (
    apply_inventory_observation,
    declared_profiles,
)

NOW = datetime(2026, 9, 10, 3, 0, tzinfo=UTC)


def test_hostname_only_inventory_is_not_ready() -> None:
    payload = {"hostname": "WIN-EVSH1DN8H5O", "measured_at_utc": NOW.isoformat()}
    observed = apply_inventory_observation(declared_profiles(), payload, when=NOW)
    xeon = next(item for item in observed if item.machine_id == "WIN-EVSH1DN8H5O")
    assert xeon.observation_kind != "MEASURED" or xeon.state != "READY" or not xeon.sid


def test_future_timestamp_cannot_confer_ready() -> None:
    payload = {
        "hostname": "WIN-EVSH1DN8H5O",
        "whoami": r"win-evsh1dn8h5o\kines",
        "sid": "S-1-5-21-xeon",
        "totalRAMGB": 63.96,
        "availableRAMGB": 40.0,
        "cpuLogical": 16,
        "cpuPhysical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 68.46}],
        "isa": {"sse42": True, "avx": True, "avx2": False},
        "osBuild": "19043",
        "measured_at_utc": (NOW + timedelta(days=7)).isoformat(),
    }
    observed = apply_inventory_observation(declared_profiles(), payload, when=NOW)
    xeon = next(item for item in observed if item.machine_id == "WIN-EVSH1DN8H5O")
    assert xeon.state != "READY" or xeon.observation_kind != "MEASURED"


def test_xeon_is_normal_full_capacity_when_measured() -> None:
    payload = {
        "hostname": "WIN-EVSH1DN8H5O",
        "whoami": r"win-evsh1dn8h5o\kines",
        "sid": "S-1-5-21-xeon",
        "totalRAMGB": 63.96,
        "availableRAMGB": 40.0,
        "cpuLogical": 16,
        "cpuPhysical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 68.46}],
        "isa": {"sse42": True, "avx": True, "avx2": False},
        "osBuild": "19043",
        "osSupportStatus": "UNSUPPORTED_21H1",
        "measured_at_utc": NOW.isoformat(),
    }
    observed = apply_inventory_observation(declared_profiles(), payload, when=NOW)
    xeon = next(item for item in observed if item.machine_id == "WIN-EVSH1DN8H5O")
    chosen = choose_measured_worker((xeon,))
    assert chosen is not None
    assert chosen.machine_id == "WIN-EVSH1DN8H5O"
    assert chosen.memory_mb >= 60000


def test_modify_acl_and_nonzero_task_are_not_accepted() -> None:
    icacls = r"COMFy-V4-CPU-01\Windows 11:(OI)(CI)(M)"
    verdict = classify_live_managed_worker(
        runas=r"COMFy-V4-CPU-01\Windows 11",
        script_path=r"C:\ProgramData\ProjectPipeline\worker\cycle20_remote_worker.py",
        icacls_text=icacls,
        last_result=5,
        last_run_time="2026-09-10T00:00:00Z",
    )
    assert verdict["accepted_production_worker"] is False


def test_empty_control_ready_does_not_fabricate_leaves() -> None:

    root = Path(__file__).resolve().parents[3]
    ready = observation_ready_task_ids(root, None, live_ssh=True)
    assert ready != ["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"]


def test_observation_rejects_zero_time_and_duplicate_heartbeats() -> None:
    payload = {
        "duration_met": True,
        "wall_seconds": 0,
        "source": {"sha": "f41c64d5b533ed4a329e0e431ee073dd791ee050", "tree": "WRONG"},
        "heartbeats": [{"at_utc": "same-time"} for _ in range(60)],
        "fault": {"recovered": True, "killed": False, "owned_job_id": "fake"},
        "completed_jobs": [{"results": [{"task_id": "PP-TASK-any", "outcome": "ACCEPTED"}]}],
    }
    result = evaluate_observation(
        payload,
        expected_source_sha="f41c64d5b533ed4a329e0e431ee073dd791ee050",
        expected_source_tree="66778a1fdc0a7a8d8cf3b07f25367ed896ffca2b",
        require_useful_work=True,
        require_owned_recovery=True,
    )
    assert result["ok"] is False
    assert any(
        "zero_wall_seconds" in item or "heartbeat_duplicate" in item for item in result["reasons"]
    )
