from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from project_pipeline.autonomy_runtime.remote_job import RemoteJobController, RemoteJobEnvelope
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
    ResourceRegistrySnapshot,
    ResourceType,
)
from project_pipeline.scheduler.admission import evaluate_admission
from project_pipeline.scheduler.fleet import (
    MachineProfile,
    bind_profile_claims,
    physical_claims_for_machine,
    resume_host,
    select_target,
)
from project_pipeline.scheduler.host_observation import classify_gpu, declared_profiles
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
    assert profiles["WIN-EVSH1DN8H5O"].state == "ENROLLMENT_PENDING"
    chosen, denials = select_target(tuple(profiles.values()), when=NOW)
    assert chosen is None
    assert any("ENROLLMENT_PENDING" in item for item in denials)
    assert any("stale_capacity" in item for item in denials)
    observed = declared_profiles(when=NOW, observation_source="test_fixture")
    chosen_observed, observed_denials = select_target(observed, when=NOW)
    assert chosen_observed is not None
    assert chosen_observed.machine_id == "COMFY-V4-CPU-01"
    assert any("ENROLLMENT_PENDING" in item for item in observed_denials)


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
