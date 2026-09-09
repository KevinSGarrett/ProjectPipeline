from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from project_pipeline.autonomy_runtime.managed_worker import (
    classify_scheduled_action,
    inspect_scheduled_task_xml,
    os_age_denies_xeon,
    owned_task_retirement_plan,
)
from project_pipeline.scheduler.admission import chosen_host_admitted, evaluate_admission
from project_pipeline.scheduler.fleet import MachineProfile, select_target
from project_pipeline.scheduler.host_observation import (
    apply_inventory_observation,
    declared_profiles,
    measure_local_inventory,
)

NOW = datetime(2026, 9, 8, tzinfo=UTC)
SHA = "a" * 40
TREE = "b" * 40
XEON = "WIN-EVSH1DN8H5O"


def _measured_xeon() -> MachineProfile:
    inventory = {
        "hostname": XEON,
        "whoami": r"win-evsh1dn8h5o\kines",
        "sid": "S-1-5-21-xeon",
        "totalRAMGB": 63.96,
        "availableRAMGB": 48.0,
        "cpuLogical": 16,
        "cpuPhysical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 68.46}],
        "isa": {"sse42": True, "avx": True, "avx2": False},
        "gpus": [{"Name": "NVIDIA Quadro 6000"}],
        "osBuild": "19043",
        "osSupportStatus": "UNSUPPORTED_21H1",
        "measured_at_utc": NOW.isoformat(),
    }
    observed = apply_inventory_observation(declared_profiles(), inventory, when=NOW)
    return {item.machine_id: item for item in observed}[XEON]


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
    record = {
        "c18_disposition": "PM_ACCEPTED",
        "reviewer_id": "rev",
        "implementer_id": "impl",
        "source_sha": SHA,
        "source_tree": TREE,
        "hosts": {
            XEON: {
                "state": "READY",
                "freshness": "fresh",
                "observation_kind": "MEASURED",
                "observed_at_utc": "1970-01-01T00:00:00+00:00",
            }
        },
    }
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
    plan = owned_task_retirement_plan("ProjectPipelineFleetWorkerXeon")
    assert plan["ok"] is True
    assert plan["unrelated_services_untouched"] is True
    assert "/DISABLE" in plan["disable_argv"]
    stray = owned_task_retirement_plan("SomeOtherTask")
    assert stray["ok"] is False


def test_system_sid_with_pp_jobs_is_not_production_worker() -> None:
    verdict = classify_scheduled_action(
        runas="S-1-5-18",
        script_path=r"C:\Users\kines\pp_jobs\run_index.cmd",
        acl_fullcontrol_users=(),
    )
    assert verdict["accepted_production_worker"] is False


def test_xeon_has_no_legacy_memory_ceiling() -> None:
    xeon = _measured_xeon()
    assert xeon.memory_mb > 48000
    pools = {pool.resource_type.value: pool for pool in xeon.physical_pools()}
    assert pools["MEMORY_MB"].capacity_units == xeon.memory_mb


def test_os_age_does_not_cap_or_strip_xeon() -> None:
    from project_pipeline.autonomy_runtime.managed_worker import os_age_policy

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
    record = {
        "c18_disposition": "PM_ACCEPTED",
        "reviewer_id": "rev",
        "implementer_id": "impl",
        "source_sha": SHA,
        "source_tree": TREE,
        "hosts": {
            XEON: {
                "state": "READY",
                "freshness": "fresh",
                "observed_at_utc": NOW.isoformat(),
            }
        },
    }
    denied = chosen_host_admitted(record, XEON, expected_sha=SHA, expected_tree=TREE, now=NOW)
    assert denied["ok"] is False


def test_aged_measured_observation_is_stale() -> None:
    record = {
        "c18_disposition": "PM_ACCEPTED",
        "reviewer_id": "rev",
        "implementer_id": "impl",
        "source_sha": SHA,
        "source_tree": TREE,
        "hosts": {
            XEON: {
                "state": "READY",
                "freshness": "fresh",
                "observation_kind": "MEASURED",
                "observed_at_utc": (NOW - timedelta(hours=3)).isoformat(),
            }
        },
    }
    denied = chosen_host_admitted(record, XEON, expected_sha=SHA, expected_tree=TREE, now=NOW)
    assert denied["ok"] is False
