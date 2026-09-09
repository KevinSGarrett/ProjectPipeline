from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from project_pipeline.autonomy_runtime.remote_job import RemoteJobController, RemoteJobEnvelope
from project_pipeline.autonomy_runtime.ssh_dispatch import (
    SSH_CLIENT_ENV_KEYS,
    SshDispatchAdapter,
    build_ssh_argv,
    remote_command_allowed,
)
from project_pipeline.autonomy_runtime.worker_supervision import (
    recover_isolated_job,
    start_isolated_job,
)
from project_pipeline.command_center.api import CommandCenterAuth, create_command_center_app
from project_pipeline.command_center.fleet import FleetRegistry
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import HealthDimension, HealthState
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.domain.scheduler import (
    AccessMode,
    ResourceClaim,
    ResourceLease,
    ResourceRegistrySnapshot,
    ResourceType,
    scheduler_identifier,
)
from project_pipeline.scheduler.admission import (
    chosen_host_admitted,
    evaluate_admission,
    observation_admission_record,
)
from project_pipeline.scheduler.fleet import (
    MachineProfile,
    bind_profile_claims,
    fleet_projection,
    occupancy_from_leases,
    physical_claims_for_machine,
    resume_host,
    select_target,
)
from project_pipeline.scheduler.host_observation import (
    apply_inventory_observation,
    classify_gpu,
    declared_profiles,
    enrollment_blockers,
)
from project_pipeline.scheduler.resources import admission_reasons

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _profile(machine_id: str, **overrides: object) -> MachineProfile:
    payload = {
        "machine_id": machine_id,
        "hostname": machine_id,
        "role": "CPU_WORKER",
        "observed_at_utc": NOW,
        "isa_flags": ("avx",),
        "cpu_slots": 8,
        "memory_mb": 32000,
        "disk_mb": 20000,
        "principal": "worker",
    }
    payload.update(overrides)
    return MachineProfile.model_validate(payload)


def test_unregistered_physical_pool_is_denied() -> None:
    registry = ResourceRegistrySnapshot.create(pools=())
    claims = physical_claims_for_machine("WIN-EVSH1DN8H5O")
    reasons = admission_reasons(claims, registry, when=NOW)
    assert any(item.startswith("unregistered_pool:") for item in reasons)


def test_wrong_machine_and_overcommit_are_denied() -> None:
    pools = _profile("COMFY-V4-CPU-01").physical_pools()
    registry = ResourceRegistrySnapshot.create(pools=pools)
    claims = physical_claims_for_machine("WIN-EVSH1DN8H5O")
    wrong = admission_reasons(claims, registry, when=NOW)
    assert any(item.startswith("unregistered_pool:") for item in wrong)
    local_claims = (
        ResourceClaim(
            resource_key="COMFY-V4-CPU-01/cpu_slots",
            resource_type=ResourceType.CPU_SLOT,
            access_mode=AccessMode.SHARED,
            quantity=999,
            machine_id="COMFY-V4-CPU-01",
        ),
    )
    over = admission_reasons(local_claims, registry, when=NOW)
    assert any(item.startswith("capacity:") for item in over)
    mismatched = (
        ResourceClaim(
            resource_key="COMFY-V4-CPU-01/cpu_slots",
            resource_type=ResourceType.CPU_SLOT,
            access_mode=AccessMode.SHARED,
            quantity=1,
            machine_id="WIN-EVSH1DN8H5O",
        ),
    )
    crossed = admission_reasons(mismatched, registry, when=NOW)
    assert any(item.startswith("wrong_machine:") for item in crossed)


def test_legacy_quadro_is_rejected_for_modern_cuda() -> None:
    xeon = _profile(
        "WIN-EVSH1DN8H5O",
        cuda_compute_capability=2.0,
        gpu_name="Quadro 6000",
        modern_cuda_eligible=False,
        isa_flags=("avx",),
    )
    laptop = _profile(
        "PRIMARY-CODEX-WORKSTATION",
        role="PRIMARY_CONTROL_CANDIDATE",
        modern_cuda_eligible=True,
        cuda_compute_capability=12.0,
        gpu_name="RTX 5060",
        isa_flags=("avx", "avx2"),
    )
    chosen, denials = select_target(
        (xeon, laptop), when=NOW, require_modern_cuda=True, prefer_roles=("GPU_WORKER",)
    )
    assert chosen is None or chosen.machine_id == "PRIMARY-CODEX-WORKSTATION"
    assert any("unsupported_gpu" in item for item in denials)


def test_stale_and_drained_hosts_are_denied() -> None:
    stale = _profile("COMFY-V4-CPU-01", observed_at_utc=NOW - timedelta(hours=2))
    drained = _profile("WIN-EVSH1DN8H5O", state="DRAINED")
    chosen, denials = select_target((stale, drained), when=NOW)
    assert chosen is None
    assert any("stale_capacity" in item for item in denials)
    assert any("DRAINED" in item for item in denials)


def test_avx2_requirement_rejects_sandy_bridge() -> None:
    xeon = _profile("WIN-EVSH1DN8H5O", isa_flags=("avx",))
    chosen, denials = select_target((xeon,), when=NOW, require_avx2=True)
    assert chosen is None
    assert any("unsupported_isa:avx2" in item for item in denials)


def test_remote_job_accepts_once_and_rejects_tamper_and_wrong_host(tmp_path: Path) -> None:
    workspace = tmp_path / "job"
    workspace.mkdir()
    envelope = RemoteJobEnvelope(
        job_id="job-1",
        host_id="COMFY-V4-CPU-01",
        profile_id="cpu",
        principal="worker",
        lease_id="LEASE-AAAAAAAAAAAAAAAAAAAA",
        fence="fence-1",
        source_sha="a" * 40,
        source_tree="b" * 40,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=(sys.executable, "-c", "print('ok')"),
        workspace=str(workspace),
        deadline_utc=NOW + timedelta(minutes=5),
        cpu_ceiling=2,
        memory_mb_ceiling=1024,
        correlation_id="corr-1",
    )
    controller = RemoteJobController()
    executed = controller.execute(envelope, now=NOW)
    assert executed["outcome"] == "EXECUTED"
    result = executed["result"]
    first = controller.accept(envelope, result, expected_host="COMFY-V4-CPU-01", now=NOW)
    assert first["outcome"] == "ACCEPTED"
    replay = controller.accept(envelope, result, expected_host="COMFY-V4-CPU-01", now=NOW)
    assert replay["duplicate"] is True
    tampered = result.model_copy(update={"output_sha256": "e" * 64})
    conflict = controller.accept(envelope, tampered, expected_host="COMFY-V4-CPU-01", now=NOW)
    assert conflict["reason"] == "conflicting_replay"
    wrong = controller.accept(envelope, result, expected_host="WIN-EVSH1DN8H5O", now=NOW)
    assert wrong["reason"] == "wrong_host"
    controller.expire_fence("fence-1")
    expired = controller.accept(envelope, result, expected_host="COMFY-V4-CPU-01", now=NOW)
    assert expired["reason"] == "expired_fence"
    mismatched = result.model_copy(update={"job_id": "job-other"})
    controller_fresh = RemoteJobController()
    wrong_job = controller_fresh.accept(
        envelope, mismatched, expected_host="COMFY-V4-CPU-01", now=NOW
    )
    assert wrong_job["reason"] == "wrong_job"


def test_isolated_worker_process_loss_recovers_without_reboot(tmp_path: Path) -> None:
    workspace = tmp_path / "proc"
    workspace.mkdir()
    process = start_isolated_job([sys.executable, "-c", "import time; time.sleep(30)"], workspace)
    recovered = recover_isolated_job(process)
    assert recovered["ok"] is True
    assert recovered["running"] is False
    assert recovered["affected_lane_only"] is True


def test_fleet_api_drain_resume_changes_state() -> None:
    profile = _profile("COMFY-V4-CPU-01", observed_at_utc=datetime.now(UTC))
    registry = FleetRegistry((profile,))
    snapshot = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:fleet",
        project_id="PROJECT-PIPELINE",
        operating_mode="NORMAL",
        health=(HealthDimension(name="control", state=HealthState.HEALTHY, reason="ok"),),
    )
    app = create_command_center_app(
        snapshot_provider=lambda: snapshot,
        event_broker=RealtimeEventBroker(),
        inbox=AttentionNotificationBroker(),
        auth=CommandCenterAuth(lambda token: "actor:test" if token == "good" else None),
        fleet_registry=registry,
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer good"}
    listed = client.get("/api/v1/command-center/fleet", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["hosts"][0]["freshness"] == "fresh"
    drained = client.post("/api/v1/command-center/fleet/COMFY-V4-CPU-01/drain", headers=headers)
    assert drained.status_code == 200
    assert drained.json()["profile"]["state"] == "DRAINED"
    resumed = client.post("/api/v1/command-center/fleet/COMFY-V4-CPU-01/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["profile"]["state"] == "READY"
    denied = client.get("/api/v1/command-center/fleet")
    assert denied.status_code == 401


def test_resume_of_enrollment_pending_host_is_denied() -> None:
    pending = _profile("WIN-EVSH1DN8H5O", state="ENROLLMENT_PENDING")
    registry = FleetRegistry((pending,))
    denied = registry.resume("WIN-EVSH1DN8H5O", actor="actor:test")
    assert denied["ok"] is False
    assert "ENROLLMENT_PENDING" in str(denied["reason"])
    assert registry.profiles()[0].state == "ENROLLMENT_PENDING"


def test_quadro_is_not_modern_cuda() -> None:
    classification = classify_gpu(name="NVIDIA Quadro 6000", compute_capability=2.0)
    assert classification["modern_cuda_eligible"] is False


def test_declared_xeon_is_enrollment_pending() -> None:
    profiles = {item.machine_id: item for item in declared_profiles()}
    xeon = profiles["WIN-EVSH1DN8H5O"]
    assert xeon.state == "READY"
    assert xeon.principal == r"win-evsh1dn8h5o\kines"
    assert profiles["COMFY-V4-CPU-01"].principal == r"comfy-v4-cpu-01\windows 11"
    assert enrollment_blockers() == ()
    assert "avx2" not in {flag.lower() for flag in xeon.isa_flags}
    chosen, denials = select_target(tuple(profiles.values()), when=NOW)
    assert chosen is None
    assert any("stale_capacity" in item for item in denials)
    observed = declared_profiles(when=NOW, observation_source="test_fixture")
    chosen_observed, _observed_denials = select_target(observed, when=NOW)
    assert chosen_observed is not None
    assert chosen_observed.machine_id == "WIN-EVSH1DN8H5O"
    cuda_chosen, cuda_reasons = select_target(observed, when=NOW, require_modern_cuda=True)
    assert cuda_chosen is None or cuda_chosen.machine_id != "WIN-EVSH1DN8H5O"
    assert any("unsupported_gpu" in item for item in cuda_reasons)


def test_declared_profiles_are_stale_without_observation_source() -> None:
    profiles = declared_profiles(when=NOW)
    assert all(not item.fresh_at(NOW) for item in profiles)
    observed = declared_profiles(when=NOW, observation_source="test_fixture")
    assert all(item.fresh_at(NOW) for item in observed)


def test_resume_does_not_refresh_stale_observation() -> None:
    stale = _profile("COMFY-V4-CPU-01", observed_at_utc=NOW - timedelta(hours=2), state="DRAINED")
    resumed = resume_host(stale, when=NOW)
    assert resumed.state == "READY"
    assert resumed.observed_at_utc == stale.observed_at_utc
    assert resumed.fresh_at(NOW) is False


def test_fleet_registry_persists_drain_to_shared_state(tmp_path: Path) -> None:
    path = tmp_path / "fleet_state.json"
    profile = _profile("COMFY-V4-CPU-01", observed_at_utc=NOW)
    first = FleetRegistry((profile,), persist_path=path)
    drained = first.drain("COMFY-V4-CPU-01", actor="actor:test")
    assert drained["ok"] is True
    second = FleetRegistry.load_or_declared(path, declared_profiles())
    assert second.profiles()[0].state == "DRAINED"
    assert second.profiles()[0].machine_id == "COMFY-V4-CPU-01"


def test_bind_profile_claims_rewrites_local_machine() -> None:
    from project_pipeline.domain.scheduler import SchedulerTaskProfile

    profile = SchedulerTaskProfile(
        task_id="PP-TASK-000510",
        project_id="PROJECT-PIPELINE",
        sequence_rank=1,
        utility_score=1,
        priority="P1",
        claims=(
            ResourceClaim(
                resource_key="machine:local/cpu_slots",
                resource_type=ResourceType.CPU_SLOT,
                access_mode=AccessMode.SHARED,
                quantity=1,
                machine_id="machine:local",
            ),
        ),
    )
    bound = bind_profile_claims(profile, "COMFY-V4-CPU-01")
    assert bound.claims[0].machine_id == "COMFY-V4-CPU-01"
    assert bound.claims[0].resource_key == "COMFY-V4-CPU-01/cpu_slots"


_SHA = "a" * 40
_TREE = "b" * 40


def _admission_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "c18_disposition": "PM_ACCEPTED_WITH_FOLLOWUP",
        "reviewer_id": "isolated-pm-disposition-c19-2652b873",
        "implementer_id": "cursor-implementer-c19-c18-correction",
        "source_sha": _SHA,
        "source_tree": _TREE,
        "hosts": {"COMFY-V4-CPU-01": {"state": "READY", "freshness": "fresh"}},
    }
    record.update(overrides)
    return record


def _evaluate_admission(record: dict[str, object] | None) -> dict[str, object]:
    return evaluate_admission(record, expected_sha=_SHA, expected_tree=_TREE)


def test_missing_admission_record_denies_remote_placement() -> None:
    result = _evaluate_admission(None)
    assert result["c18_accepted"] is False
    assert result["remote_ok"] is False
    assert "admission_record_missing" in result["failures"]


def test_independent_c18_followup_does_not_admit_unenrolled_hosts() -> None:
    result = _evaluate_admission(
        _admission_record(
            hosts={
                "WIN-EVSH1DN8H5O": {"state": "ENROLLMENT_PENDING", "freshness": "unknown"},
                "COMFY-V4-CPU-01": {"state": "READY", "freshness": "stale"},
            }
        )
    )
    assert result["c18_accepted"] is True
    assert result["remote_ok"] is False
    assert any("remote_denied:WIN-EVSH1DN8H5O" in item for item in result["failures"])


def test_self_authored_acceptance_is_not_independent() -> None:
    result = _evaluate_admission(
        _admission_record(
            c18_disposition="PM_ACCEPTED",
            reviewer_id="cursor-implementer-c19-c18-correction",
        )
    )
    assert result["c18_accepted"] is False
    assert "independent_reviewer_missing" in result["failures"]


def test_fresh_enrolled_worker_is_remotely_admitted() -> None:
    result = _evaluate_admission(_admission_record())
    assert result["c18_accepted"] is True
    assert result["remote_ok"] is True
    assert result["failures"] == ()


def test_chosen_host_must_be_the_admitted_worker() -> None:
    record = _admission_record()
    allowed = chosen_host_admitted(
        record, "COMFY-V4-CPU-01", expected_sha=_SHA, expected_tree=_TREE
    )
    assert allowed["ok"] is True
    denied = chosen_host_admitted(record, "WIN-EVSH1DN8H5O", expected_sha=_SHA, expected_tree=_TREE)
    assert denied["ok"] is False
    assert any("unchosen_host:WIN-EVSH1DN8H5O" in item for item in denied["failures"])
    malformed = chosen_host_admitted(
        _admission_record(hosts={"COMFY-V4-CPU-01": {"state": "BROKEN", "freshness": "recent"}}),
        "COMFY-V4-CPU-01",
        expected_sha=_SHA,
        expected_tree=_TREE,
    )
    assert malformed["ok"] is False
    assert any(
        "remote_denied:COMFY-V4-CPU-01:BROKEN:recent" in item for item in malformed["failures"]
    )


def test_inventory_observation_admits_xeon_cpu_not_cuda() -> None:
    inventory = {
        "hostname": "WIN-EVSH1DN8H5O",
        "whoami": r"win-evsh1dn8h5o\kines",
        "totalRAMGB": 63.96,
        "cpuLogical": 16,
        "disks": [{"DeviceID": "C:", "FreeGB": 68.46}],
        "gpus": [{"Name": "NVIDIA Quadro 6000"}],
        "isa": {"sse42": True, "avx": True, "avx2": False},
    }
    observed = apply_inventory_observation(declared_profiles(), inventory, when=NOW)
    xeon = {item.machine_id: item for item in observed}["WIN-EVSH1DN8H5O"]
    assert xeon.fresh_at(NOW) is True
    assert xeon.modern_cuda_eligible is False
    assert "avx2" not in xeon.isa_flags
    chosen, _denials = select_target(observed, when=NOW)
    assert chosen is not None
    assert chosen.machine_id == "WIN-EVSH1DN8H5O"
    cuda_chosen, cuda_reasons = select_target(observed, when=NOW, require_modern_cuda=True)
    assert cuda_chosen is None or cuda_chosen.machine_id != "WIN-EVSH1DN8H5O"
    assert any("unsupported_gpu" in item for item in cuda_reasons)


def test_ssh_dispatch_builds_argv_without_env_or_kevin_principal(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("not-a-real-key\n", encoding="utf-8")
    argv = build_ssh_argv(
        identity=identity,
        user="kines",
        host="100.107.207.66",
        remote_argv=["hostname"],
        remote_cwd=r"C:\Users\kines\pp_jobs",
    )
    assert "PROGRAMDATA" in SSH_CLIENT_ENV_KEYS
    assert argv[0] == "ssh"
    assert "-i" in argv
    assert argv[argv.index("-l") + 1] == "kines"
    assert "100.107.207.66" in argv
    assert "kevin@" not in " ".join(argv)
    assert "kines@" not in " ".join(argv)
    assert remote_command_allowed(("hostname",)) is True
    assert remote_command_allowed(("python", r"C:\Users\kines\pp_jobs\job.py")) is True
    assert remote_command_allowed(("python", "-c", "print(1)")) is False
    assert remote_command_allowed(("python", "-c", "__import__('os').system('whoami')")) is False
    try:
        build_ssh_argv(
            identity=identity,
            user="kevin",
            host="100.107.207.66",
            remote_argv=["hostname"],
            remote_cwd=r"C:\Users\kines\pp_jobs",
        )
    except ValueError as error:
        assert "kevin@" in str(error)
    else:
        raise AssertionError("kevin@ principal must be rejected")


def test_ssh_adapter_execute_uses_injected_runner(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("not-a-real-key\n", encoding="utf-8")

    class _Completed:
        returncode = 0
        stdout = "WIN-EVSH1DN8H5O\n"
        stderr = ""

    def _runner(*_args: object, **_kwargs: object) -> _Completed:
        return _Completed()

    adapter = SshDispatchAdapter(identity=identity, runner=_runner)
    payload = adapter.execute(
        command=["hostname"],
        working_directory=Path(r"C:\Users\kines\pp_jobs"),
    )
    assert payload["exit_code"] == 0
    assert payload["transport"] == "openssh_tailscale"
    assert "USERPROFILE" not in json.dumps(payload)
    envelope = RemoteJobEnvelope(
        job_id="job-ssh-1",
        host_id="WIN-EVSH1DN8H5O",
        profile_id="memory-cpu",
        principal=r"win-evsh1dn8h5o\kines",
        lease_id="LEASE-BBBBBBBBBBBBBBBBBBBB",
        fence="fence-ssh",
        source_sha="a" * 40,
        source_tree="b" * 40,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=("hostname",),
        workspace=r"C:\Users\kines\pp_jobs",
        deadline_utc=NOW + timedelta(minutes=5),
        cpu_ceiling=2,
        memory_mb_ceiling=1024,
        correlation_id="corr-ssh",
    )
    controller = RemoteJobController(adapter)
    executed = controller.execute(envelope, now=NOW)
    assert executed["outcome"] == "EXECUTED"
    accepted = controller.accept(
        envelope, executed["result"], expected_host="WIN-EVSH1DN8H5O", now=NOW
    )
    assert accepted["outcome"] == "ACCEPTED"


def test_timed_out_remote_job_is_unknown_outcome(tmp_path: Path) -> None:
    workspace = tmp_path / "job"
    workspace.mkdir()

    class _TimeoutAdapter:
        def execute(self, **_kwargs: object) -> dict[str, object]:
            return {"timed_out": True, "exit_code": 124}

    envelope = RemoteJobEnvelope(
        job_id="job-timeout",
        host_id="WIN-EVSH1DN8H5O",
        profile_id="memory-cpu",
        principal=r"win-evsh1dn8h5o\kines",
        lease_id="LEASE-CCCCCCCCCCCCCCCCCCCC",
        fence="fence-timeout",
        source_sha="a" * 40,
        source_tree="b" * 40,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=(sys.executable, "-c", "print('ok')"),
        workspace=str(workspace),
        deadline_utc=NOW + timedelta(minutes=5),
        cpu_ceiling=1,
        memory_mb_ceiling=512,
        correlation_id="corr-timeout",
    )
    result = RemoteJobController(_TimeoutAdapter()).execute(envelope, now=NOW)
    assert result["outcome"] == "UNKNOWN_OUTCOME"
    assert result["reason"] == "lost_acknowledgement"


def test_fresh_xeon_host_is_remotely_admitted() -> None:
    record = _admission_record(
        hosts={
            "WIN-EVSH1DN8H5O": {"state": "READY", "freshness": "fresh"},
            "COMFY-V4-CPU-01": {"state": "STALE", "freshness": "stale"},
        }
    )
    result = _evaluate_admission(record)
    assert result["c18_accepted"] is True
    assert result["remote_ok"] is True
    allowed = chosen_host_admitted(
        record, "WIN-EVSH1DN8H5O", expected_sha=_SHA, expected_tree=_TREE
    )
    assert allowed["ok"] is True
    denied = chosen_host_admitted(record, "COMFY-V4-CPU-01", expected_sha=_SHA, expected_tree=_TREE)
    assert denied["ok"] is False


def test_observation_does_not_mint_c18_acceptance() -> None:
    minted = observation_admission_record(
        {},
        hosts={"WIN-EVSH1DN8H5O": {"state": "READY", "freshness": "fresh"}},
        source_sha=_SHA,
        source_tree=_TREE,
    )
    result = _evaluate_admission(minted)
    assert result["c18_accepted"] is False
    assert "c18_acceptance_missing" in result["failures"]
    copied = observation_admission_record(
        {
            "c18_disposition": "PM_ACCEPTED_WITH_FOLLOWUP",
            "reviewer_id": "isolated-pr158-reviewer",
            "implementer_id": "cursor-implementer-c19-c18-correction",
        },
        hosts={"WIN-EVSH1DN8H5O": {"state": "READY", "freshness": "fresh"}},
        source_sha=_SHA,
        source_tree=_TREE,
    )
    copied_result = _evaluate_admission(copied)
    assert copied_result["c18_accepted"] is True


def test_ssh_timeout_expired_text_buffers_are_not_decoded(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("not-a-real-key\n", encoding="utf-8")

    def _runner(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=1, output="partial", stderr="late")

    adapter = SshDispatchAdapter(identity=identity, runner=_runner)
    payload = adapter.execute(
        command=["hostname"],
        working_directory=Path(r"C:\Users\kines\pp_jobs"),
    )
    assert payload["timed_out"] is True
    assert payload["exit_code"] == 124
    assert payload["stdout"] == "partial"
    assert payload["stderr"] == "late"


def test_remote_controller_rejects_envelope_host_mismatch(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("not-a-real-key\n", encoding="utf-8")

    def _runner(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("SSH must not run for the wrong host")

    envelope = RemoteJobEnvelope(
        job_id="job-wrong-host",
        host_id="COMFY-V4-CPU-01",
        profile_id="cpu",
        principal="worker:comfy",
        lease_id="LEASE-DDDDDDDDDDDDDDDDDDDD",
        fence="fence-wrong",
        source_sha="a" * 40,
        source_tree="b" * 40,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=("hostname",),
        workspace=r"C:\Users\kines\pp_jobs",
        deadline_utc=NOW + timedelta(minutes=5),
        cpu_ceiling=1,
        memory_mb_ceiling=512,
        correlation_id="corr-wrong",
    )
    executed = RemoteJobController(SshDispatchAdapter(identity=identity, runner=_runner)).execute(
        envelope, now=NOW
    )
    assert executed["outcome"] == "REJECTED"
    assert executed["reason"] == "wrong_host"


def test_inventory_observation_admits_comfy_cpu_not_cuda() -> None:
    inventory = {
        "hostname": "comfy-v4-cpu-01",
        "whoami": r"comfy-v4-cpu-01\windows 11",
        "totalRAMGB": 31.79,
        "cpuLogical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 28.5}],
        "gpus": [{"Name": "Intel(R) UHD Graphics 630"}],
        "isa": {"sse42": True, "avx": True, "avx2": True},
    }
    observed = apply_inventory_observation(declared_profiles(), inventory, when=NOW)
    comfy = {item.machine_id: item for item in observed}["COMFY-V4-CPU-01"]
    assert comfy.fresh_at(NOW) is True
    assert comfy.modern_cuda_eligible is False
    assert "avx2" in {flag.lower() for flag in comfy.isa_flags}
    assert comfy.principal.lower() == r"comfy-v4-cpu-01\windows 11"
    chosen, _denials = select_target(observed, when=NOW)
    assert chosen is not None
    assert chosen.machine_id == "COMFY-V4-CPU-01"
    cuda_chosen, cuda_reasons = select_target(observed, when=NOW, require_modern_cuda=True)
    assert cuda_chosen is None or cuda_chosen.machine_id != "COMFY-V4-CPU-01"
    assert any("unsupported_gpu" in item for item in cuda_reasons)


def test_comfy_ssh_uses_windows_11_login_and_rejects_denied_principals(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("not-a-real-key\n", encoding="utf-8")
    argv = build_ssh_argv(
        identity=identity,
        user="Windows 11",
        host="100.77.151.3",
        remote_argv=["hostname"],
        remote_cwd=r"C:\Users\Windows 11\pp_jobs",
    )
    assert argv[argv.index("-l") + 1] == "Windows 11"
    assert "100.77.151.3" in argv
    assert "kevin@" not in " ".join(argv)
    assert "kines@" not in " ".join(argv)
    for denied_user in ("kevin", "kines"):
        try:
            build_ssh_argv(
                identity=identity,
                user=denied_user,
                host="100.77.151.3",
                remote_argv=["hostname"],
                remote_cwd=r"C:\Users\Windows 11\pp_jobs",
            )
        except ValueError as error:
            assert denied_user in str(error).lower()
        else:
            raise AssertionError(f"{denied_user}@ principal must be rejected on COMFY")


def test_ssh_adapter_for_machine_binds_comfy(tmp_path: Path) -> None:
    identity = tmp_path / "id_ed25519"
    identity.write_text("not-a-real-key\n", encoding="utf-8")

    class _Completed:
        returncode = 0
        stdout = "comfy-v4-cpu-01\n"
        stderr = ""

    def _runner(*_args: object, **_kwargs: object) -> _Completed:
        return _Completed()

    adapter = SshDispatchAdapter.for_machine("COMFY-V4-CPU-01", identity=identity, runner=_runner)
    assert adapter.machine_id == "COMFY-V4-CPU-01"
    assert adapter.user == "Windows 11"
    payload = adapter.execute(
        command=["hostname"],
        working_directory=Path(r"C:\Users\Windows 11\pp_jobs"),
    )
    assert payload["exit_code"] == 0
    envelope = RemoteJobEnvelope(
        job_id="job-comfy-1",
        host_id="COMFY-V4-CPU-01",
        profile_id="cpu",
        principal=r"comfy-v4-cpu-01\windows 11",
        lease_id="LEASE-EEEEEEEEEEEEEEEEEEEE",
        fence="fence-comfy",
        source_sha="a" * 40,
        source_tree="b" * 40,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=("hostname",),
        workspace=r"C:\Users\Windows 11\pp_jobs",
        deadline_utc=NOW + timedelta(minutes=5),
        cpu_ceiling=1,
        memory_mb_ceiling=512,
        correlation_id="corr-comfy",
    )
    executed = RemoteJobController(adapter).execute(envelope, now=NOW)
    assert executed["outcome"] == "EXECUTED"
    assert executed["result"].host_id == "COMFY-V4-CPU-01"


def test_inventory_observation_preserves_drained_comfy() -> None:
    inventory = {
        "hostname": "COMFY-V4-CPU-01",
        "whoami": r"comfy-v4-cpu-01\windows 11",
        "totalRAMGB": 31.79,
        "cpuLogical": 8,
        "disks": [{"DeviceID": "C:", "FreeGB": 28.5}],
        "gpus": [{"Name": "Intel(R) UHD Graphics 630"}],
        "isa": {"sse42": True, "avx": True, "avx2": True},
    }
    profiles = tuple(
        item.model_copy(update={"state": "DRAINED"})
        if item.machine_id == "COMFY-V4-CPU-01"
        else item
        for item in declared_profiles()
    )
    observed = apply_inventory_observation(profiles, inventory, when=NOW)
    comfy = {item.machine_id: item for item in observed}["COMFY-V4-CPU-01"]
    assert comfy.state == "DRAINED"
    assert comfy.fresh_at(NOW) is True
    chosen, denials = select_target(observed, when=NOW)
    assert chosen is None or chosen.machine_id != "COMFY-V4-CPU-01"
    assert any("host_state:DRAINED" in item or "COMFY-V4-CPU-01" in item for item in denials)


def _lease(machine_id: str, task_id: str, *, token: int = 1) -> ResourceLease:
    claim = physical_claims_for_machine(machine_id)[0]
    return ResourceLease(
        lease_id=scheduler_identifier("LEASE", machine_id, task_id, str(token)),
        task_id=task_id,
        holder_id=f"worker:{machine_id}",
        claim=claim,
        fencing_token=token,
        acquired_at_utc=NOW,
        expires_at_utc=NOW + timedelta(minutes=15),
    )


def test_missing_occupancy_stays_unknown_not_green() -> None:
    rows = fleet_projection((_profile("WIN-EVSH1DN8H5O"),), when=NOW)
    assert rows[0]["active_jobs"] == "unknown"
    assert rows[0]["lease_id"] == "unknown"
    assert rows[0]["assignment"] == "unknown"


def test_idle_occupancy_is_zero_none_not_unknown() -> None:
    rows = fleet_projection((_profile("WIN-EVSH1DN8H5O"),), when=NOW, occupancy={})
    assert rows[0]["active_jobs"] == 0
    assert rows[0]["lease_id"] == "none"
    assert rows[0]["assignment"] == "none"


def test_lease_occupancy_binds_jobs_and_does_not_paint_other_hosts() -> None:
    xeon = _profile("WIN-EVSH1DN8H5O")
    comfy = _profile("COMFY-V4-CPU-01")
    occupancy = occupancy_from_leases((_lease("WIN-EVSH1DN8H5O", "PP-TASK-000512"),))
    rows = {
        row["machine_id"]: row
        for row in fleet_projection((xeon, comfy), when=NOW, occupancy=occupancy)
    }
    assert rows["WIN-EVSH1DN8H5O"]["active_jobs"] == 1
    assert rows["WIN-EVSH1DN8H5O"]["assignment"] == "PP-TASK-000512"
    assert rows["WIN-EVSH1DN8H5O"]["lease_id"].startswith("LEASE-")
    assert rows["COMFY-V4-CPU-01"]["active_jobs"] == 0
    assert rows["COMFY-V4-CPU-01"]["lease_id"] == "none"


def test_fleet_api_binds_lease_occupancy() -> None:
    profile = _profile("COMFY-V4-CPU-01", observed_at_utc=datetime.now(UTC))
    registry = FleetRegistry((profile,))
    lease = _lease("COMFY-V4-CPU-01", "PP-TASK-000515")
    snapshot = CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:fleet-occupancy",
        project_id="PROJECT-PIPELINE",
        operating_mode="NORMAL",
        health=(HealthDimension(name="control", state=HealthState.HEALTHY, reason="ok"),),
    )
    app = create_command_center_app(
        snapshot_provider=lambda: snapshot,
        event_broker=RealtimeEventBroker(),
        inbox=AttentionNotificationBroker(),
        auth=CommandCenterAuth(lambda token: "actor:test" if token == "good" else None),
        fleet_registry=registry,
        occupancy_provider=lambda: occupancy_from_leases((lease,)),
    )
    listed = TestClient(app).get(
        "/api/v1/command-center/fleet", headers={"Authorization": "Bearer good"}
    )
    assert listed.status_code == 200
    host = listed.json()["hosts"][0]
    assert host["active_jobs"] == 1
    assert host["assignment"] == "PP-TASK-000515"
    assert host["lease_id"].startswith("LEASE-")
