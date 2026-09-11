"""Production-path regressions for independent Cycle 21 PM source findings."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from project_pipeline.autonomy_runtime import context_validation as cv
from project_pipeline.autonomy_runtime import remote_worker_protocol as wp
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.fleet_loop import _enrich_dispatched, _resource_metrics
from project_pipeline.autonomy_runtime.managed_worker import classify_live_managed_worker
from project_pipeline.autonomy_runtime.observation_eval import evaluate_observation
from project_pipeline.autonomy_runtime.remote_job import (
    RemoteJobController,
    RemoteJobEnvelope,
    RemoteJobResult,
)
from project_pipeline.autonomy_runtime.task_execution_specs import (
    VALIDATION_ALPHA_TASK,
    VALIDATION_BETA_TASK,
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
    env = RemoteJobEnvelope.model_validate(args)
    wp.write_lease_grant(work, {**args, "status": "ACTIVE"})
    return env


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


def test_src02_worker_measures_source_identity() -> None:
    from project_pipeline.autonomy_runtime.worker_runtime_identity import (
        local_runtime_identity,
        measured_source_identity,
    )

    sha, tree = measured_source_identity(
        protocol_file=str(
            SOURCE / "src" / "project_pipeline" / "autonomy_runtime" / "worker_runtime_identity.py"
        )
    )
    assert len(sha) == 40
    assert len(tree) == 40
    live = local_runtime_identity(
        protocol_file=str(
            SOURCE / "src" / "project_pipeline" / "autonomy_runtime" / "worker_runtime_identity.py"
        )
    )
    assert live["source_sha"] == sha
    assert live["source_tree"] == tree


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

    live_ok = {
        "hostname": HOST,
        "principal": PRINCIPAL,
        "sid": "S-1-5-21-review",
        "module_sha256": wp.module_sha256(wp.__file__),
        "source_sha": SHA,
        "source_tree": TREE,
    }
    with (
        patch.object(wp, "local_runtime_identity", return_value=live_ok),
        patch.object(wp, "_spawn_enforced", side_effect=interrupted_spawn),
        patch.object(wp, "process_creation_filetime", return_value="5678"),
    ):
        first_worker = wp.run_envelope(worker_payload)
        second_worker = wp.run_envelope(worker_payload)
    assert first_worker.get("ok") is False
    assert first_worker.get("reason") == "unknown_outcome"
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
    nested = _resource_metrics(
        {HOST: {"totalRAMGB": 32, "availableRAMGB": 20}},
        {HOST: {"totalRAMGB": 32, "availableRAMGB": 31}},
        [
            {
                "results": [
                    {
                        "host_id": HOST,
                        "executed": {
                            "rss_samples_mb": [64, 96],
                            "scratch_bytes": 2048,
                        },
                        "started_at_utc": NOW.isoformat(),
                        "ended_at_utc": (NOW + timedelta(seconds=10)).isoformat(),
                    }
                ]
            }
        ],
        transfer_seconds=12,
    )
    assert nested["peak_ram_mb"] == 96
    assert nested["scratch_bytes"] == 2048


def test_spawn_enforced_queries_peak_before_closing_handle() -> None:
    source = inspect.getsource(wp._spawn_enforced)
    assert source.index("query_job_peak_memory_bytes") < source.index("close_job_handle")


def test_isolated_graph_does_not_write_jira_issue_files(tmp_path: Path) -> None:
    from project_pipeline.autonomy_runtime.isolated_validation_graph import (
        ensure_isolated_validation_graph,
    )
    from project_pipeline.control.kernel import ProjectControlKernel
    from project_pipeline.overlay import control_input_root
    from project_pipeline.persistence import SQLiteStateStore
    from project_pipeline.services.state import CoreStateService

    database = tmp_path / "state.sqlite3"
    with SQLiteStateStore(database, SOURCE) as store:
        store.initialize()
        CoreStateService(store, SOURCE).initialize_from_repository()
    installed = ensure_isolated_validation_graph(SOURCE, database)
    assert installed.get("ok") is True
    tasks = control_input_root(SOURCE) / "jira" / "tasks"
    assert not (tasks / f"{VALIDATION_ALPHA_TASK}.json").exists()
    with SQLiteStateStore(database, SOURCE) as store:
        project_id = str(installed["project_id"])
        facts = {
            item.task_id: item
            for item in ProjectControlKernel(SOURCE, store, project_id).task_facts()
        }
    assert VALIDATION_ALPHA_TASK in facts
    assert facts[VALIDATION_ALPHA_TASK].product_scope_allowed is True


def test_verified_predecessor_unblocks_dependent(tmp_path: Path) -> None:
    from project_pipeline.autonomy_runtime.fleet_loop import control_ready_task_ids
    from project_pipeline.autonomy_runtime.isolated_validation_graph import (
        ensure_isolated_validation_graph,
        mark_verified_predecessor,
    )
    from project_pipeline.domain.state import TaskLifecycleState
    from project_pipeline.persistence import SQLiteStateStore
    from project_pipeline.services.state import CoreStateService

    database = tmp_path / "state.sqlite3"
    with SQLiteStateStore(database, SOURCE) as store:
        store.initialize()
        CoreStateService(store, SOURCE).initialize_from_repository()
    assert ensure_isolated_validation_graph(SOURCE, database).get("ok") is True
    first = control_ready_task_ids(SOURCE, database)
    assert VALIDATION_ALPHA_TASK in first
    assert VALIDATION_BETA_TASK not in first
    mark_verified_predecessor(SOURCE, database, VALIDATION_ALPHA_TASK)
    with SQLiteStateStore(database, SOURCE) as store:
        alpha = store.get_task_state(VALIDATION_ALPHA_TASK)
        beta = store.get_task_state(VALIDATION_BETA_TASK)
    assert alpha is not None and alpha.state is TaskLifecycleState.DONE
    assert beta is not None and beta.state is TaskLifecycleState.READY
    second = control_ready_task_ids(SOURCE, database)
    assert VALIDATION_BETA_TASK in second
    assert VALIDATION_ALPHA_TASK not in second


def test_envelope_lease_grant_is_not_independent_authority(tmp_path: Path) -> None:
    work = tmp_path / "forged-grant"
    work.mkdir()
    payload = _env(tmp_path, "forged-grant-env").model_dump(mode="json")
    payload["argv"] = list(_env(tmp_path, "forged-grant-env").argv)
    payload["workspace"] = str(work)
    payload["workspace_root"] = str(tmp_path)
    payload["job_id"] = "forged-grant-env"
    payload["lease_grant"] = {
        "lease_id": payload["lease_id"],
        "fence": payload["fence"],
        "job_id": payload["job_id"],
        "host_id": HOST,
        "status": "ACTIVE",
        "source_sha": SHA,
        "source_tree": TREE,
        "overlay_sha256": "c" * 64,
    }
    assert not (work / "lease_grant.json").exists()
    launches: list[object] = []

    def fake_spawn(**kwargs: object) -> tuple[object, dict[str, object]]:
        launches.append(kwargs)
        done = SimpleNamespace(returncode=0, stdout="forged", stderr="", output_truncated=False)
        return done, {"pid": 1, "creation_time": "1", "mechanism": "intercept"}

    live = {
        "hostname": HOST,
        "principal": PRINCIPAL,
        "sid": "S-1-5-21-review",
        "module_sha256": wp.module_sha256(wp.__file__),
        "source_sha": SHA,
        "source_tree": TREE,
    }
    with (
        patch.object(wp, "local_runtime_identity", return_value=live),
        patch.object(wp, "_spawn_enforced", side_effect=fake_spawn),
    ):
        result = wp.run_envelope(payload)
    assert result.get("ok") is False
    assert result.get("reason") == "scheduler_authority_unverified"
    assert launches == []


def test_missing_jobs_db_lease_consults_scheduler_database(tmp_path: Path) -> None:
    import sqlite3

    sched = tmp_path / "scheduler.sqlite3"
    connected = sqlite3.connect(sched)
    connected.execute(
        """
        CREATE TABLE scheduler_resource_leases (
            lease_id TEXT PRIMARY KEY,
            fencing_token TEXT,
            expires_at_utc TEXT NOT NULL,
            released_at_utc TEXT
        )
        """
    )
    env = _env(tmp_path, "fallback-lease")
    connected.execute(
        """
        INSERT INTO scheduler_resource_leases
            (lease_id, fencing_token, expires_at_utc, released_at_utc)
        VALUES (?, ?, ?, NULL)
        """,
        (env.lease_id, env.fence, (NOW + timedelta(hours=1)).isoformat()),
    )
    connected.commit()
    connected.close()
    jobs = FleetJobStore(tmp_path / "jobs.sqlite3", scheduler_database=sched)
    jobs.remember_scheduler_lease("OTHER-LEASE", "OTHER-FENCE", now=NOW)
    jobs.persist_intent(env.model_dump(mode="json"), now=NOW)
    accepted = jobs.accept_result(
        {
            "job_id": env.job_id,
            "host_id": env.host_id,
            "fence": env.fence,
            "exit_code": 0,
            "output_sha256": "a" * 64,
            "stdout_sha256": "b" * 64,
            "stderr_sha256": "c" * 64,
        },
        now=NOW,
        envelope=env.model_dump(mode="json"),
    )
    assert accepted.get("outcome") == "ACCEPTED"


def test_enrich_reads_nested_receipt_and_producer_metrics() -> None:
    item = _enrich_dispatched(
        VALIDATION_ALPHA_TASK,
        {
            "outcome": "ACCEPTED",
            "executed": {
                "context_consumption": {"ok": True, "job_id": VALIDATION_ALPHA_TASK},
                "rss_samples_mb": [12.5],
                "scratch_bytes": 32,
                "started_at_utc": NOW.isoformat(),
                "ended_at_utc": NOW.isoformat(),
            },
        },
        HOST,
    )
    assert item["context_consumption"]["ok"] is True
    assert item["rss_samples_mb"] == [12.5]
    assert item["scratch_bytes"] == 32
    assert item["started_at_utc"]
