"""Cycle 21 fleet lifecycle, admission, managed worker, and recovery."""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.fleet_loop import (
    _cli_status_from_process,
    _machine_for_task,
    choose_measured_worker,
    cycle_owned_validation_jobs,
    observation_ready_task_ids,
    run_observation,
)
from project_pipeline.autonomy_runtime.managed_worker import classify_live_managed_worker
from project_pipeline.autonomy_runtime.observation_eval import evaluate_observation
from project_pipeline.domain.identifiers import IdentifierKind, validate_identifier
from project_pipeline.scheduler.fleet import MachineProfile
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
    owned = cycle_owned_validation_jobs(())
    assert "PP-TASK-000516" not in owned


def test_cycle_owned_jobs_bind_both_hosts() -> None:
    now = datetime(2026, 9, 10, 3, 0, tzinfo=UTC)
    xeon = MachineProfile.model_validate(
        {
            "machine_id": "WIN-EVSH1DN8H5O",
            "hostname": "WIN-EVSH1DN8H5O",
            "role": "MEMORY_HEAVY_BATCH_WORKER",
            "observed_at_utc": now,
            "isa_flags": ("avx",),
            "cpu_slots": 8,
            "memory_mb": 64000,
            "disk_mb": 70000,
            "principal": r"win-evsh1dn8h5o\kines",
            "observation_kind": "MEASURED",
            "sid": "S-1-5-21-xeon",
        }
    )
    comfy = MachineProfile.model_validate(
        {
            "machine_id": "COMFY-V4-CPU-01",
            "hostname": "COMFY-V4-CPU-01",
            "role": "CPU_WORKER",
            "observed_at_utc": now,
            "isa_flags": ("avx2",),
            "cpu_slots": 8,
            "memory_mb": 32000,
            "disk_mb": 40000,
            "principal": r"comfy-v4-cpu-01\windows 11",
            "observation_kind": "MEASURED",
            "sid": "S-1-5-21-comfy",
        }
    )
    jobs = cycle_owned_validation_jobs((xeon, comfy))
    assert jobs == ["PP-TASK-000990", "PP-TASK-000991"]
    assert _machine_for_task(jobs[0], (xeon, comfy), index=0, remote=True) == "WIN-EVSH1DN8H5O"
    assert _machine_for_task(jobs[1], (xeon, comfy), index=1, remote=True) == "COMFY-V4-CPU-01"
    for task_id in jobs:
        assert validate_identifier(task_id, IdentifierKind.ISSUE) == task_id


def test_noncanonical_cycle_job_id_cannot_lease() -> None:
    with pytest.raises(ValueError, match="Invalid issue identifier"):
        validate_identifier("PP-TASK-C21-VALIDATE-COMFY", IdentifierKind.ISSUE)


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


def test_operator_surfaces_invoke_production_status_cli() -> None:
    source = inspect.getsource(_cli_status_from_process)
    assert "fleet-loop" in source
    assert "status" in source
    assert "raw_decode" in source


def test_observation_staggers_cycle_owned_jobs() -> None:
    source = inspect.getsource(run_observation)
    assert "pending_owned" in source
    assert "elapsed >= 45" in source
    assert "CYCLE_OWNED_VALIDATION_JOBS" in source


def test_observation_result_persists_resource_metrics() -> None:
    source = inspect.getsource(run_observation)
    assert '"resources": resources' in source
    assert "cli_ui_independent" in source


def test_production_fleet_loop_cli_forwards_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from project_pipeline import cli as pipeline_cli

    dest = tmp_path / "observe.json"
    captured: list[list[str]] = []

    def fake_main(argv: list[str] | None = None) -> int:
        args = list(argv or [])
        captured.append(args)
        dest.write_text('{"ok": true, "evaluation": {"ok": true}}\n', encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.fleet_loop.main",
        fake_main,
    )
    code = pipeline_cli.main(
        [
            "fleet-loop",
            "observe",
            "--root",
            str(tmp_path),
            "--json-output",
            str(dest),
            "--live-ssh",
            "--duration-seconds",
            "3600",
        ]
    )
    assert code == 0
    assert dest.is_file()
    assert captured
    argv = captured[0]
    assert "--json-output" in argv
    assert str(dest) in argv
    assert "--live-ssh" in argv


def test_fleet_loop_status_and_run_write_json_output(tmp_path: Path) -> None:
    from project_pipeline.autonomy_runtime.fleet_loop import main as fleet_loop_main

    status_dir = tmp_path / ".local" / "cycle21_observation"
    status_dir.mkdir(parents=True)
    (status_dir / "status.json").write_text(
        json.dumps({"remaining_seconds": 12, "fault": {"kind": "owned_durable_fault"}}) + "\n",
        encoding="utf-8",
    )
    dest = tmp_path / "status-out.json"
    code = fleet_loop_main(["status", "--root", str(tmp_path), "--json-output", str(dest)])
    assert code == 0
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["remaining_seconds"] == 12
    source = inspect.getsource(fleet_loop_main)
    assert "_persist_json_output(args.json_output, result)" in source
    assert source.count("_persist_json_output(args.json_output") >= 3
