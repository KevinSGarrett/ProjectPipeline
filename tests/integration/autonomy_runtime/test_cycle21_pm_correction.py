"""Production-path regressions for independent Cycle 21 PM source findings."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from project_pipeline.autonomy_runtime import context_validation as cv
from project_pipeline.autonomy_runtime import remote_worker_protocol as wp
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.fleet_loop import _resource_metrics
from project_pipeline.autonomy_runtime.managed_worker import classify_live_managed_worker
from project_pipeline.autonomy_runtime.observation_eval import evaluate_observation
from project_pipeline.autonomy_runtime.remote_job import (
    RemoteJobController,
    RemoteJobEnvelope,
    RemoteJobResult,
)
from project_pipeline.autonomy_runtime.task_execution_specs import (
    VALIDATION_ALPHA_TASK,
    required_tests,
)
from project_pipeline.scheduler.fleet import physical_claims_for_machine, select_target
from project_pipeline.scheduler.host_observation import profile_from_comfy_inventory
from project_pipeline.scheduler.persistence import SchedulerStore

SOURCE = Path(__file__).resolve().parents[3]
SHA = "5c671ecac4b7d266cacaddfb0e49b0dd1a8ad423"
TREE = "f17866e4f81881d39bc29854d088fecab8aa2be0"
HOST = "COMFY-V4-CPU-01"
PRINCIPAL = r"comfy-v4-cpu-01\windows 11"
NOW = datetime.now(UTC)


def _env(base: Path, name: str, **changes: object) -> RemoteJobEnvelope:
    work = base / name
    work.mkdir(exist_ok=True)
    args: dict[str, object] = dict(
        job_id=name,
        host_id=HOST,
        profile_id="CPU_WORKER",
        principal=PRINCIPAL,
        lease_id="LEASE-REVIEW",
        fence="FENCE-REVIEW",
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=("python", r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py"),
        workspace=str(work),
        workspace_root=str(base),
        deadline_utc=NOW + timedelta(minutes=15),
        cpu_ceiling=1,
        memory_mb_ceiling=256,
        correlation_id="cycle21-pm-correction",
    )
    args.update(changes)
    return RemoteJobEnvelope.model_validate(args)


def _result(envelope: RemoteJobEnvelope, digest: str = "e" * 64) -> RemoteJobResult:
    return RemoteJobResult(
        job_id=envelope.job_id,
        host_id=envelope.host_id,
        fence=envelope.fence,
        exit_code=0,
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        output_sha256=digest,
    )


def test_src01_no_native_pass_default() -> None:
    tests = required_tests(VALIDATION_ALPHA_TASK)
    assert tests != (cv.NATIVE_PASS,)
    assert tests[0].endswith("cycle21_selected_alpha.py")
    try:
        required_tests("PP-TASK-000516")
    except ValueError as error:
        assert "no_execution_spec" in str(error)
    else:
        raise AssertionError("production owners must not default to NATIVE_PASS")


def test_src04_and_src05_context_and_skip(tmp_path: Path) -> None:
    live = {
        "hostname": HOST,
        "principal": PRINCIPAL,
        "sid": "S-1-5-21-review",
        "module_sha256": "a" * 64,
    }
    compiled = cv.compile_validation_pack(
        root=SOURCE,
        database=tmp_path / "context.sqlite3",
        task_id="PP-TASK-000521",
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        selection=(cv.NATIVE_PASS,),
        host_id=HOST,
        principal=PRINCIPAL,
    )
    pack = compiled["pack"]
    consume = dict(
        pack_path=str(tmp_path / "context_pack.json"),
        workspace=str(tmp_path),
        pack_sha256=compiled["pack_sha256"],
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        host_id=HOST,
        principal=PRINCIPAL,
        job_id="PP-TASK-000521",
        project_id="PROJECT-PIPELINE",
    )
    with patch.object(cv, "local_runtime_identity", return_value=live):
        cv.write_pack(tmp_path, pack)
        assert cv.consume_pack_on_worker(consume).get("ok") is True
        assert cv.consume_pack_on_worker({**consume, "job_id": "PP-TASK-000999"}).get("ok") is False
        old = copy.deepcopy(pack)
        old["generated_at_utc"] = (NOW - timedelta(days=5)).isoformat()
        cv.write_pack(tmp_path, old)
        assert cv.consume_pack_on_worker(consume).get("ok") is False
        old["generated_at_utc"] = (NOW + timedelta(days=365)).isoformat()
        cv.write_pack(tmp_path, old)
        future = cv.consume_pack_on_worker(consume)
        assert future.get("ok") is False
        assert cv.pack_content_digest(old) != compiled["pack_sha256"]

    mixed = (
        b"<testsuite><testcase name='pass'/><testcase name='mandatory'><skipped/></testcase>"
        b"</testsuite>"
    )

    def fake_pytest(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        junit = Path(
            next(
                str(item).split("=", 1)[1]
                for item in command
                if str(item).startswith("--junitxml=")
            )
        )
        junit.parent.mkdir(parents=True, exist_ok=True)
        junit.write_bytes(mixed)
        return subprocess.CompletedProcess(command, 0, "1 passed, 1 skipped", "")

    with patch.object(cv.subprocess, "run", side_effect=fake_pytest):
        native = cv.execute_native_tests(
            root=SOURCE,
            selection=("required-pass", "required-skipped"),
            output_dir=tmp_path / "mixed",
        )
    assert native.get("ok") is False
    assert native.get("status") == "MANDATORY_SKIPPED"


def test_src02_and_src03_authority_and_unknown_outcome(tmp_path: Path) -> None:
    jobs = FleetJobStore(tmp_path / "accept.sqlite3")
    envelope = _env(
        tmp_path, "altered-output", require_context_consumption=True, pack_sha256="c" * 64
    )
    jobs.persist_intent(envelope.model_dump(mode="json"), now=NOW)
    original = b"<testsuite><testcase name='real-run'/></testsuite>"
    changed = b"<testsuite><testcase name='different-run'/></testsuite>"
    accepted = RemoteJobController(store=jobs, require_intent=True).accept(
        envelope,
        _result(envelope, hashlib.sha256(original).hexdigest()),
        expected_host=HOST,
        now=NOW,
        artifact_bytes=changed,
        context_consumption={
            "ok": True,
            "pack_sha256": "0" * 64,
            "job_id": "WRONG-JOB",
            "host_id": "WRONG-HOST",
        },
    )
    assert accepted.get("outcome") != "ACCEPTED"

    revoked = _env(tmp_path, "positive-revoked")
    jobs.persist_intent(revoked.model_dump(mode="json"), now=NOW)
    jobs.expire_fence(revoked.fence, now=NOW)
    rev = RemoteJobController(store=jobs, require_intent=True).accept(
        revoked, _result(revoked), expected_host=HOST, now=NOW
    )
    assert rev.get("outcome") != "ACCEPTED"

    live = {
        "hostname": HOST,
        "principal": PRINCIPAL,
        "sid": "S-1-5-21-review",
        "module_sha256": "a" * 64,
    }
    wrong = _env(
        tmp_path,
        "wrong-runtime",
        source_sha="9" * 40,
        source_tree="8" * 40,
        lease_id="NONEXISTENT-SCHEDULER-LEASE",
        fence="REVOKED-UPSTREAM-NOT-IN-LOCAL-CACHE",
    )
    payload = wrong.model_dump(mode="json")
    payload["argv"] = list(wrong.argv)
    launches: list[object] = []

    def fake_spawn(**kwargs: object) -> tuple[object, dict[str, object]]:
        launches.append(kwargs)
        done = SimpleNamespace(
            returncode=0, stdout="review intercept", stderr="", output_truncated=False
        )
        return done, {"pid": 99999, "creation_time": "1234", "mechanism": "intercept-no-real-job"}

    with (
        patch.object(wp, "local_runtime_identity", return_value=live),
        patch.object(wp, "_spawn_enforced", side_effect=fake_spawn),
        patch.object(wp, "process_creation_filetime", return_value="5678"),
    ):
        first = wp.run_envelope(payload)
        wp.run_envelope(payload)
    assert first.get("ok") is False
    assert len(launches) == 0

    class LostTransport:
        remote_host = True
        machine_id = HOST
        count = 0

        def execute(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            self.count += 1
            raise OSError("intercepted transport failed after remote launch")

    transport = LostTransport()
    store = FleetJobStore(tmp_path / "transport.sqlite3")
    lost = _env(tmp_path, "oserror-after-launch")
    store.persist_intent(lost.model_dump(mode="json"), now=NOW)
    controller = RemoteJobController(transport, store=store, require_intent=True)
    first_exec = controller.execute(lost, now=NOW)
    second_exec = controller.execute(lost, now=NOW)
    assert first_exec.get("outcome") == "UNKNOWN_OUTCOME"
    assert second_exec.get("outcome") == "UNKNOWN_OUTCOME"
    assert transport.count == 1

    worker_payload = _env(tmp_path, "worker-unknown-error").model_dump(mode="json")
    worker_payload["argv"] = list(lost.argv)
    attempts: list[int] = []

    def interrupted_spawn(**kwargs: object) -> tuple[object, dict[str, object]]:
        del kwargs
        attempts.append(1)
        raise OSError("intercepted failure after a possible remote child launch")

    with (
        patch.object(wp, "local_runtime_identity", return_value=live),
        patch.object(wp, "_spawn_enforced", side_effect=interrupted_spawn),
        patch.object(wp, "process_creation_filetime", return_value="5678"),
    ):
        first_worker = wp.run_envelope(worker_payload)
        second_worker = wp.run_envelope(worker_payload)
    assert first_worker.get("ok") is False
    assert second_worker.get("ok") is False
    assert len(attempts) <= 1


def test_src02_released_scheduler_lease_rejected(tmp_path: Path) -> None:
    inventory = dict(
        hostname=HOST,
        whoami=PRINCIPAL,
        sid="S-1-5-21-review",
        totalRAMGB=32,
        availableRAMGB=0.001,
        cpuLogical=8,
        cpuPhysical=8,
        disks=[{"FreeGB": 100}],
        isa={"avx": True, "avx2": True},
        measured_at_utc=NOW.isoformat(),
        observation_kind="MEASURED",
    )
    profile = profile_from_comfy_inventory(inventory, when=NOW)
    assert profile is not None
    with SchedulerStore(tmp_path / "resources.sqlite3", SOURCE) as scheduler:
        scheduler.ensure_machine_pools(profile.physical_pools())
        claim = scheduler.acquire_bundle(
            task_id="PP-TASK-000521",
            holder_id="reviewer",
            claims=physical_claims_for_machine(HOST, cpu=1, memory_mb=4096),
            now=NOW,
        )
        assert claim.acquired is False
        ok_claim = scheduler.acquire_bundle(
            task_id="PP-TASK-000521",
            holder_id="reviewer",
            claims=physical_claims_for_machine(HOST, cpu=1, memory_mb=1),
            now=NOW,
        )
        assert ok_claim.acquired is True
        lease = ok_claim.leases[0]
        jobs = FleetJobStore(tmp_path / "released-scheduler.sqlite3")
        envelope = _env(
            tmp_path,
            VALIDATION_ALPHA_TASK,
            lease_id=lease.lease_id,
            fence=str(lease.fencing_token),
        )
        jobs.persist_intent(envelope.model_dump(mode="json"), now=NOW)
        scheduler.release_lease(
            lease.lease_id,
            holder_id="reviewer",
            fencing_token=lease.fencing_token,
            now=NOW,
        )
        accepted = RemoteJobController(store=jobs, require_intent=True).accept(
            envelope, _result(envelope), expected_host=HOST, now=NOW
        )
        assert accepted.get("outcome") != "ACCEPTED"


def test_src06_measured_available_ram_denies_overcommit(tmp_path: Path) -> None:
    inventory = dict(
        hostname=HOST,
        whoami=PRINCIPAL,
        sid="S-1-5-21-review",
        totalRAMGB=32,
        availableRAMGB=0.001,
        cpuLogical=8,
        cpuPhysical=8,
        disks=[{"FreeGB": 100}],
        isa={"avx": True, "avx2": True},
        measured_at_utc=NOW.isoformat(),
        observation_kind="MEASURED",
    )
    profile = profile_from_comfy_inventory(inventory, when=NOW)
    assert profile is not None
    chosen, _denials = select_target((profile,), when=NOW)
    assert chosen is not None
    with SchedulerStore(tmp_path / "overcommit.sqlite3", SOURCE) as scheduler:
        scheduler.ensure_machine_pools(profile.physical_pools())
        claim = scheduler.acquire_bundle(
            task_id="PP-TASK-000521",
            holder_id="reviewer",
            claims=physical_claims_for_machine(HOST, cpu=1, memory_mb=4096),
            now=NOW,
        )
        assert claim.acquired is False


def test_src06_accepts_when_capacity_exists(tmp_path: Path) -> None:
    inventory = dict(
        hostname=HOST,
        whoami=PRINCIPAL,
        sid="S-1-5-21-review",
        totalRAMGB=32,
        availableRAMGB=8,
        cpuLogical=8,
        cpuPhysical=8,
        disks=[{"FreeGB": 100}],
        isa={"avx": True, "avx2": True},
        measured_at_utc=NOW.isoformat(),
        observation_kind="MEASURED",
    )
    profile = profile_from_comfy_inventory(inventory, when=NOW)
    assert profile is not None
    with SchedulerStore(tmp_path / "enough.sqlite3", SOURCE) as scheduler:
        scheduler.ensure_machine_pools(profile.physical_pools())
        claim = scheduler.acquire_bundle(
            task_id=VALIDATION_ALPHA_TASK,
            holder_id="reviewer",
            claims=physical_claims_for_machine(HOST, cpu=1, memory_mb=256),
            now=NOW,
        )
        assert claim.acquired is True


def test_src08_unknown_task_result_is_not_accepted() -> None:
    acl = "BUILTIN\\Administrators:(F)\nNT AUTHORITY\\SYSTEM:(F)\nCOMFY-V4-CPU-01\\worker:(RX)\n"
    unknown = classify_live_managed_worker(
        runas=PRINCIPAL,
        script_path=r"C:\ProgramData\ProjectPipeline\worker\cycle20_remote_worker.py",
        icacls_text=acl,
        last_result="not-observed",
        last_run_time="",
    )
    assert unknown.get("accepted_production_worker") is False
    running = classify_live_managed_worker(
        runas=PRINCIPAL,
        script_path=r"C:\ProgramData\ProjectPipeline\worker\cycle20_remote_worker.py",
        icacls_text=acl,
        last_result="267009",
        last_run_time="",
    )
    assert running.get("reason") != "task_result_unknown"


def test_src07_evaluator_and_metrics(tmp_path: Path) -> None:
    mixed = (
        b"<testsuite><testcase name='pass'/><testcase name='mandatory'><skipped/></testcase>"
        b"</testsuite>"
    )
    artifact = tmp_path / "borrowed_junit.xml"
    artifact.write_bytes(mixed)
    digest = hashlib.sha256(mixed).hexdigest()
    payload = dict(
        duration_met=True,
        wall_seconds=3600,
        source={"sha": SHA, "tree": TREE},
        overlay={"digest": "c" * 64},
        heartbeats=[{"at_utc": (NOW + timedelta(seconds=i * 60)).isoformat()} for i in range(60)],
        fault=dict(
            recovered=True,
            killed=True,
            owned_job_id="unbound",
            intent_preserved=True,
            reconcile_reason="claimed",
            recovered_output_accepted=True,
            unaffected_lane_progress=True,
            controller_restarted=True,
        ),
        completed_jobs=[
            {
                "results": [
                    dict(
                        task_id="PP-TASK-000990",
                        outcome="ACCEPTED",
                        tests_run=2,
                        host_id=host,
                        acquired_junit_path=str(artifact),
                        artifact_sha256=digest,
                    )
                    for host in (HOST, "WIN-EVSH1DN8H5O")
                ]
            }
        ],
        resources=dict(peak_ram_mb=1, scratch_bytes=1, transfer_seconds=1, concurrency=2),
    )
    evaluated = evaluate_observation(
        payload,
        expected_source_sha=SHA,
        expected_source_tree=TREE,
        expected_overlay_sha256="c" * 64,
    )
    assert evaluated.get("ok") is False
    metrics = _resource_metrics(
        {HOST: {"totalRAMGB": 32, "availableRAMGB": 20}},
        {HOST: {"totalRAMGB": 32, "availableRAMGB": 31}},
        [
            {
                "results": [
                    {
                        "host_id": HOST,
                        "rss_samples_mb": [120, 256],
                        "scratch_bytes": 4096,
                        "started_at_utc": NOW.isoformat(),
                        "ended_at_utc": (NOW + timedelta(seconds=10)).isoformat(),
                    }
                ]
            }
        ],
        transfer_seconds=100,
    )
    assert metrics["peak_ram_mb"] == 256
    assert metrics["scratch_bytes"] == 4096
    assert metrics["transfer_seconds"] == 100
    assert metrics["concurrency"] == 1
    assert metrics["host_count"] == 1
    dumped = json.dumps(payload["completed_jobs"], default=str)
    assert metrics["scratch_bytes"] != len(dumped)
