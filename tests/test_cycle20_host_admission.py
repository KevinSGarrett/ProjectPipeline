from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from project_pipeline.autonomy_runtime.fleet_loop import (
    choose_measured_worker,
    profiles_from_inventories,
)
from project_pipeline.autonomy_runtime.managed_worker import (
    classify_live_managed_worker,
    classify_scheduled_action,
    inspect_scheduled_task_xml,
    os_age_denies_xeon,
    os_age_policy,
    owned_task_query_argv,
    owned_task_retirement_plan,
    parse_icacls_fullcontrol_users,
)
from project_pipeline.scheduler.admission import chosen_host_admitted, evaluate_admission
from project_pipeline.scheduler.fleet import MachineProfile, select_target
from project_pipeline.scheduler.host_observation import (
    COMFY_MACHINE_ID,
    apply_inventory_observation,
    declared_profiles,
    measure_local_inventory,
)

NOW = datetime(2026, 9, 8, tzinfo=UTC)
SHA = "a" * 40
TREE = "b" * 40
XEON = "WIN-EVSH1DN8H5O"


def _xeon_inventory() -> dict[str, object]:
    return {
        "hostname": XEON,
        "whoami": r"win-evsh1dn8h5o\kines",
        "sid": "S-1-5-21-xeon",
        "totalRAMGB": 63.96,
        "availableRAMGB": 40.0,
        "cpuLogical": 16,
        "cpuPhysical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 68.46}],
        "isa": {"sse42": True, "avx": True, "avx2": False},
        "gpus": [{"Name": "NVIDIA Quadro 6000"}],
        "osBuild": "19043",
        "osSupportStatus": "UNSUPPORTED_21H1",
        "measured_at_utc": NOW.isoformat(),
    }


def _measured_xeon() -> MachineProfile:
    observed = apply_inventory_observation(declared_profiles(), _xeon_inventory(), when=NOW)
    return {item.machine_id: item for item in observed}[XEON]


def _c18_record(host: dict[str, object]) -> dict[str, object]:
    return {
        "c18_disposition": "PM_ACCEPTED",
        "reviewer_id": "rev",
        "implementer_id": "impl",
        "source_sha": SHA,
        "source_tree": TREE,
        "hosts": {XEON: host},
    }


def _ready_host(**extra: object) -> dict[str, object]:
    host: dict[str, object] = {
        "state": "READY",
        "freshness": "fresh",
        "observed_at_utc": NOW.isoformat(),
    }
    host.update(extra)
    return host


def test_measurement_time_is_not_ingest_time() -> None:
    payload = measure_local_inventory(
        query=lambda _script: json.dumps(
            {
                "hostname": "KEVIN",
                "whoami": "operator",
                "sid": "S-1-5-21-laptop",
                "totalRAMGB": 31.8,
                "availableRAMGB": 12.0,
                "cpuLogical": 16,
                "cpuPhysical": 8,
                "osBuild": "26100",
                "disks": [{"DeviceID": "C:", "FreeGB": 180.0}],
                "measured_at_utc": "2026-09-08T00:00:01+00:00",
            }
        )
    )
    assert payload["ok"] is True
    assert payload["measured_at_utc"] == "2026-09-08T00:00:01+00:00"
    assert payload["disks"][0]["FreeGB"] != 200000


def test_os_age_alone_does_not_deny_xeon() -> None:
    xeon = _measured_xeon()
    assert xeon.os_support_status == "UNSUPPORTED_21H1"
    assert os_age_denies_xeon(xeon.os_support_status, xeon.machine_id) is False
    chosen, denials = select_target((xeon,), when=NOW)
    assert chosen is not None
    assert chosen.machine_id == XEON
    assert all("os" not in item.lower() or "unsupported_gpu" in item for item in denials)


def test_hostname_only_and_stale_and_future_are_ineligible() -> None:
    declared = declared_profiles(when=NOW, observation_source="reingest.json")
    laptop = {item.machine_id: item for item in declared}["PRIMARY-CODEX-WORKSTATION"]
    assert laptop.observation_kind == "DECLARED"
    assert laptop.fresh_at(NOW) is False
    assert laptop.disk_mb == 200000
    chosen, denials = select_target(declared, when=NOW)
    assert chosen is None
    assert any("measurement_incomplete" in item for item in denials)
    stale = _measured_xeon().model_copy(
        update={"observed_at_utc": datetime(1970, 1, 1, tzinfo=UTC), "observation_kind": "PARTIAL"}
    )
    chosen_stale, stale_denials = select_target((stale,), when=NOW)
    assert chosen_stale is None
    assert any(
        "measurement_incomplete" in item or "stale_capacity" in item for item in stale_denials
    )


def test_literal_1970_freshness_is_not_admission() -> None:
    record = _c18_record(
        _ready_host(observation_kind="MEASURED", observed_at_utc="1970-01-01T00:00:00+00:00")
    )
    gate = evaluate_admission(record, expected_sha=SHA, expected_tree=TREE, now=NOW)
    assert gate["remote_ok"] is False
    denied = chosen_host_admitted(record, XEON, expected_sha=SHA, expected_tree=TREE, now=NOW)
    assert denied["ok"] is False


def test_missing_inventory_fields_are_partial() -> None:
    inventory = {"hostname": XEON}
    observed = apply_inventory_observation(declared_profiles(), inventory, when=NOW)
    xeon = {item.machine_id: item for item in observed}[XEON]
    assert xeon.observation_kind in {"PARTIAL", "DECLARED"}
    assert xeon.fresh_at(NOW) is False


def test_incompatible_avx2_and_quadro_still_denied() -> None:
    xeon = _measured_xeon()
    chosen, denials = select_target((xeon,), when=NOW, require_avx2=True)
    assert chosen is None
    assert any("unsupported_isa:avx2" in item for item in denials)
    cuda_chosen, cuda_denials = select_target((xeon,), when=NOW, require_modern_cuda=True)
    assert cuda_chosen is None or cuda_chosen.machine_id != XEON
    assert any("unsupported_gpu" in item for item in cuda_denials)


def test_scheduled_task_xml_hash_does_not_mutate_host() -> None:
    xml_text = """<?xml version="1.0"?>
<Task>
  <Principals><Principal><UserId>NT AUTHORITY\\SYSTEM</UserId></Principal></Principals>
  <Actions><Exec><Command>C:\\Users\\kines\\pp_jobs\\run_index.cmd</Command></Exec></Actions>
</Task>
"""
    inspected = inspect_scheduled_task_xml(xml_text)
    assert inspected["accepted_production_worker"] is False
    assert len(inspected["sha256"]) == 64
    verdict = classify_scheduled_action(
        runas=r"NT AUTHORITY\SYSTEM",
        script_path=r"C:\Users\kines\pp_jobs\run_index.cmd",
        acl_fullcontrol_users=("kines",),
    )
    assert verdict["accepted_production_worker"] is False
    ok = classify_scheduled_action(
        runas=r"WIN-EVSH1DN8H5O\pp-worker",
        script_path=r"C:\ProgramData\ProjectPipeline\worker\entrypoint.py",
        acl_fullcontrol_users=(),
        acl_evidence=True,
    )
    assert ok["accepted_production_worker"] is True


def test_user_pp_jobs_and_system_protected_are_rejected() -> None:
    user_pp_jobs = classify_scheduled_action(
        runas=r"WIN-EVSH1DN8H5O\kines",
        script_path=r"C:\Users\kines\pp_jobs\run_index.cmd",
        acl_fullcontrol_users=(),
    )
    assert user_pp_jobs["accepted_production_worker"] is False
    system_protected = classify_scheduled_action(
        runas=r"NT AUTHORITY\SYSTEM",
        script_path=r"C:\ProgramData\ProjectPipeline\worker\entrypoint.py",
        acl_fullcontrol_users=(),
    )
    assert system_protected["accepted_production_worker"] is False


def test_owned_task_retirement_plan_is_scoped() -> None:
    missing = owned_task_retirement_plan("ProjectPipelineFleetWorkerXeon")
    assert missing["ok"] is False
    assert missing["reason"] == "python_executable_unresolved"
    python_exe = r"C:\Users\kines\AppData\Local\Programs\Python\Python311\python.exe"
    plan = owned_task_retirement_plan(
        "ProjectPipelineFleetWorkerXeon",
        python_executable=python_exe,
    )
    assert plan["ok"] is True
    assert plan["unrelated_services_untouched"] is True
    assert "/DISABLE" in plan["disable_argv"]
    tr = plan["replacement_create_argv"][plan["replacement_create_argv"].index("/TR") + 1]
    assert python_exe in tr
    assert "--managed" in tr
    stray = owned_task_retirement_plan("SomeOtherTask", python_executable=python_exe)
    assert stray["ok"] is False


def test_system_sid_with_pp_jobs_is_not_production_worker() -> None:
    verdict = classify_scheduled_action(
        runas="S-1-5-18",
        script_path=r"C:\Users\kines\pp_jobs\run_index.cmd",
        acl_fullcontrol_users=(),
    )
    assert verdict["accepted_production_worker"] is False


def test_icacls_user_full_control_and_never_run_are_rejected() -> None:
    icacls = """
C:\\Users\\Windows 11\\ProjectPipeline\\worker NT AUTHORITY\\SYSTEM:(I)(OI)(CI)(F)
                                           BUILTIN\\Administrators:(I)(OI)(CI)(F)
                                           COMFY-V4-CPU-01\\Windows 11:(I)(OI)(CI)(F)
"""
    users = parse_icacls_fullcontrol_users(icacls)
    assert any("Windows 11" in item for item in users)
    assert not any("SYSTEM" in item.upper() for item in users)
    live = classify_live_managed_worker(
        runas="Windows 11",
        script_path=r"C:\Users\Windows 11\ProjectPipeline\worker\cycle20_remote_worker.py",
        icacls_text=icacls,
        last_result=267011,
        last_run_time="11/30/1999 12:00:00 AM",
    )
    assert live["accepted_production_worker"] is False
    assert live["never_run"] is True
    assert live["reason"] == "managed_worker_never_run"
    protected = """
C:\\ProgramData\\ProjectPipeline\\worker NT AUTHORITY\\SYSTEM:(I)(OI)(CI)(F)
                                      BUILTIN\\Administrators:(I)(OI)(CI)(F)
"""
    ok_acl = classify_live_managed_worker(
        runas=r"COMFY-V4-CPU-01\pp-worker",
        script_path=r"C:\ProgramData\ProjectPipeline\worker\cycle20_remote_worker.py",
        icacls_text=protected,
        last_result=0,
        last_run_time="9/9/2026 10:00:00 AM",
    )
    assert ok_acl["acl_fullcontrol_users"] == ()
    assert ok_acl["accepted_production_worker"] is True
    unparsed = classify_live_managed_worker(
        runas=r"COMFY-V4-CPU-01\pp-worker",
        script_path=r"C:\ProgramData\ProjectPipeline\worker\cycle20_remote_worker.py",
        icacls_text="icacls: access is denied",
        last_result=0,
        last_run_time="9/9/2026 10:00:00 AM",
    )
    assert unparsed["accepted_production_worker"] is False
    assert unparsed["reason"] == "acl_readback_required"
    assert "ProjectPipelineManagedWorkerComfy" in owned_task_query_argv(
        "ProjectPipelineManagedWorkerComfy"
    )


def test_xeon_has_no_legacy_memory_ceiling() -> None:
    xeon = _measured_xeon()
    assert xeon.memory_mb > 48000
    pools = {pool.resource_type.value: pool for pool in xeon.physical_pools()}
    assert xeon.available_memory_mb is not None
    assert pools["MEMORY_MB"].capacity_units == max(1, int(xeon.available_memory_mb))
    uncapped = xeon.model_copy(update={"available_memory_mb": 55000})
    uncapped_pools = {pool.resource_type.value: pool for pool in uncapped.physical_pools()}
    assert uncapped_pools["MEMORY_MB"].capacity_units == 55000


def test_os_age_does_not_cap_or_strip_xeon() -> None:
    xeon = _measured_xeon()
    policy = os_age_policy(xeon.machine_id, xeon.os_support_status)
    assert policy["deny"] is False
    assert policy["demote"] is False
    assert policy["memory_ceiling_mb"] is None
    assert policy["single_job_cap"] is False
    assert policy["require_duplicate_verification"] is False
    assert policy["strip_credentials"] is False
    assert xeon.eligibility_reasons(when=NOW) == ()


def test_primary_measured_disk_is_not_declared_200000() -> None:
    inventory = {
        "hostname": "KEVIN",
        "whoami": "operator:control",
        "sid": "S-1-5-21-laptop",
        "totalRAMGB": 31.8,
        "availableRAMGB": 12.0,
        "cpuLogical": 16,
        "cpuPhysical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 180.25}],
        "isa": {"sse42": True, "avx": True, "avx2": True},
        "measured_at_utc": NOW.isoformat(),
        "control_host": True,
    }
    observed = apply_inventory_observation(declared_profiles(), inventory, when=NOW)
    laptop = {item.machine_id: item for item in observed}["PRIMARY-CODEX-WORKSTATION"]
    assert laptop.observation_kind == "MEASURED"
    assert laptop.disk_mb != 200000
    assert laptop.disk_mb == int(180.25 * 1024)


def test_missing_observation_kind_is_not_measured_admission() -> None:
    denied = chosen_host_admitted(
        _c18_record(_ready_host()), XEON, expected_sha=SHA, expected_tree=TREE, now=NOW
    )
    assert denied["ok"] is False


def test_aged_measured_observation_is_stale() -> None:
    denied = chosen_host_admitted(
        _c18_record(
            _ready_host(
                observation_kind="MEASURED",
                observed_at_utc=(NOW - timedelta(hours=3)).isoformat(),
            )
        ),
        XEON,
        expected_sha=SHA,
        expected_tree=TREE,
        now=NOW,
    )
    assert denied["ok"] is False


def test_measured_admission_requires_sid_principal_and_workspace() -> None:
    denied = chosen_host_admitted(
        _c18_record(_ready_host(observation_kind="MEASURED")),
        XEON,
        expected_sha=SHA,
        expected_tree=TREE,
        now=NOW,
    )
    assert denied["ok"] is False
    allowed = chosen_host_admitted(
        _c18_record(
            _ready_host(
                observation_kind="MEASURED",
                sid="S-1-5-21-xeon",
                principal=r"win-evsh1dn8h5o\kines",
                workspace_root=r"C:\Users\kines\ProjectPipeline\jobs",
            )
        ),
        XEON,
        expected_sha=SHA,
        expected_tree=TREE,
        now=NOW,
    )
    assert allowed["ok"] is True


def test_profiles_from_inventories_keep_both_hosts_measured() -> None:
    comfy_inventory = {
        "hostname": COMFY_MACHINE_ID,
        "whoami": r"COMFY-V4-CPU-01\Windows 11",
        "sid": "S-1-5-21-comfy",
        "totalRAMGB": 31.79,
        "availableRAMGB": 20.0,
        "cpuLogical": 8,
        "cpuPhysical": 4,
        "disks": [{"DeviceID": "C:", "FreeGB": 28.5}],
        "isa": {"sse42": True, "avx": True, "avx2": True},
        "osBuild": "26100",
        "osSupportStatus": "SUPPORTED",
        "measured_at_utc": NOW.isoformat(),
    }
    profiles = profiles_from_inventories(
        {XEON: _xeon_inventory(), COMFY_MACHINE_ID: comfy_inventory},
        when=NOW,
    )
    by_id = {item.machine_id: item for item in profiles}
    assert by_id[XEON].observation_kind == "MEASURED"
    assert by_id[COMFY_MACHINE_ID].observation_kind == "MEASURED"
    assert by_id[XEON].sid == "S-1-5-21-xeon"
    assert by_id[COMFY_MACHINE_ID].sid == "S-1-5-21-comfy"
    chosen = choose_measured_worker(profiles)
    assert chosen is not None
    assert chosen.machine_id == XEON
