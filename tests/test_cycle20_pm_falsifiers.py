"""Cycle 20 PM source-review falsifiers as registered tests.

These must fail on 79fd54d and pass after the grouped production correction.
No real SSH, child launch, or process kill is performed.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import runpy
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from project_pipeline.autonomy_runtime import fleet_loop, remote_job
from project_pipeline.autonomy_runtime.dispatch_workflow import DispatchWorkflow
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.lifecycle import FleetLifecycleJournal
from project_pipeline.autonomy_runtime.managed_worker import (
    classify_scheduled_action,
    inspect_scheduled_task_xml,
    owned_task_retirement_plan,
)
from project_pipeline.autonomy_runtime.observation_eval import evaluate_observation
from project_pipeline.autonomy_runtime.remote_job import (
    RemoteJobController,
    RemoteJobEnvelope,
    RemoteJobResult,
)
from project_pipeline.autonomy_runtime.remote_worker_protocol import run_managed_worker
from project_pipeline.autonomy_runtime.ssh_dispatch import (
    SshDispatchAdapter,
    remote_command_allowed,
)
from project_pipeline.autonomy_runtime.windows_limits import limits_for_adapter
from project_pipeline.autonomy_runtime.windows_service import quote_command
from project_pipeline.autonomy_runtime.worker_entrypoint import run_envelope
from project_pipeline.overlay import refresh_instruction_manifest_hashes
from project_pipeline.scheduler.admission import write_admission_record
from project_pipeline.scheduler.fleet import MachineProfile
from project_pipeline.scheduler.persistence import SchedulerStore

SOURCE = Path(__file__).resolve().parents[1]
SHA = "79fd54daa6473e496f128d1429e37ea5f94dae09"
TREE = "b" * 40
NOW = datetime(2026, 9, 9, 14, 38, 11, tzinfo=UTC)


def _envelope(tmp_path: Path, name: str, **changes: object) -> RemoteJobEnvelope:
    workspace = tmp_path / name
    workspace.mkdir(exist_ok=True)
    values: dict[str, object] = dict(
        job_id=name,
        host_id="COMFY-V4-CPU-01",
        profile_id="CPU_WORKER",
        principal="review_fixture_worker",
        lease_id="FIXTURE_LEASE",
        fence="7",
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        input_sha256="d" * 64,
        argv=("python", "review_fixture.py"),
        workspace=str(workspace),
        workspace_root=str(tmp_path),
        deadline_utc=NOW + timedelta(minutes=5),
        cpu_ceiling=1,
        memory_mb_ceiling=64,
        correlation_id="INDEPENDENT_LOCAL_REVIEW",
    )
    values.update(changes)
    return RemoteJobEnvelope.model_validate(values)


class FakeRemote:
    remote_host = True
    machine_id = "COMFY-V4-CPU-01"

    def execute(self, **_kwargs: object) -> dict[str, object]:
        return dict(
            exit_code=0,
            timed_out=False,
            stdout_sha256="1" * 64,
            stderr_sha256="2" * 64,
            payload_sha256="3" * 64,
            remote_pid="FIXTURE_ONLY",
        )


def test_wire_includes_authority_and_rejects_nested_env_as_enforcement(
    tmp_path: Path,
) -> None:
    key = tmp_path / "placeholder-not-a-credential"
    key.write_text("not-a-real-key", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["payload"] = json.loads(str(kwargs["input"]))
        return subprocess.CompletedProcess(argv, 0, '{"ok":true,"exit_code":0}', "")

    adapter = SshDispatchAdapter.for_machine("COMFY-V4-CPU-01", identity=key, runner=fake_runner)
    store = FleetJobStore(tmp_path / "wire.sqlite3")
    env = _envelope(
        tmp_path,
        "wire",
        argv=(
            "python",
            r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle20_useful_job.py",
        ),
    )
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    RemoteJobController(adapter, store=store, require_intent=True).execute(env, now=NOW)
    required = {
        "lease_id",
        "fence",
        "source_sha",
        "source_tree",
        "profile_id",
        "principal",
        "overlay_sha256",
        "deadline_utc",
        "cpu_ceiling",
        "memory_mb_ceiling",
    }
    payload = captured["payload"]
    assert isinstance(payload, dict)
    missing = sorted(required - payload.keys())
    assert missing == []
    ssh_argv = captured["argv"]
    assert isinstance(ssh_argv, list)
    assert any(
        "ProgramData" in str(item) and "cycle20_remote_worker.py" in str(item) for item in ssh_argv
    )
    assert any(str(item).lower().endswith("python.exe") for item in ssh_argv)
    limits = limits_for_adapter(
        adapter=adapter, cpu_ceiling=1, memory_mb_ceiling=1, deadline_seconds=1
    )
    assert not (limits.get("ok") and limits.get("handle") is None)
    assert remote_command_allowed(("python", r"C:\unapproved\arbitrary.py")) is False


def test_standalone_worker_rejects_unbacked_authority_and_unowned_pid(tmp_path: Path) -> None:
    namespace = {}
    exec((SOURCE / "scripts" / "cycle20_remote_worker.py").read_text(encoding="utf-8"), namespace)
    calls: list[dict[str, object]] = []

    def fake_process(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"argv": argv, "cwd": kwargs.get("cwd"), "timeout": kwargs.get("timeout")})
        return subprocess.CompletedProcess(argv, 0, "fixture-ok", "")

    workspace = tmp_path / "outside_declared_workspace_root"
    payload = dict(
        action="execute",
        argv=["python", "arbitrary.py"],
        workspace=str(workspace),
        workspace_root=str(tmp_path / "approved_root"),
        job_id="same-job",
        input_sha256="e" * 64,
        host_id="WRONG_HOST",
        lease_id="REVOKED_LEASE",
        fence="REVOKED_FENCE",
        deadline_utc="2000-01-01T00:00:00Z",
        memory_mb_ceiling=1,
        cpu_ceiling=1,
    )
    for _ in range(2):
        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch("subprocess.run", side_effect=fake_process),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            namespace["main"]()
    assert calls == []
    kill_calls: list[list[str]] = []

    def fake_kill(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        kill_calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    with (
        patch("sys.stdin", io.StringIO(json.dumps({"action": "kill", "pid": 424242}))),
        patch("subprocess.run", side_effect=fake_kill),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        namespace["main"]()
    assert kill_calls == []


def test_changed_intent_and_unbacked_result_are_rejected(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "authority.sqlite3")
    env = _envelope(tmp_path, "original")
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    altered = env.model_copy(
        update={
            "input_sha256": "e" * 64,
            "profile_id": "UNAUTHORIZED_PROFILE",
            "argv": ("python", "different_unapproved.py"),
        }
    )
    controller = RemoteJobController(
        FakeRemote(),
        store=store,
        require_intent=True,
        expected_source_sha=SHA,
        expected_source_tree=TREE,
    )
    result = controller.execute(altered, now=NOW)
    assert result["outcome"] != "EXECUTED"
    absent = _envelope(tmp_path, "no-intent", output_contract_sha256="3" * 64)
    supplied = RemoteJobResult(
        job_id=absent.job_id,
        host_id=absent.host_id,
        fence=absent.fence,
        exit_code=0,
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        output_sha256="3" * 64,
    )
    accepted = controller.accept(absent, supplied, expected_host=absent.host_id, now=NOW)
    assert accepted["outcome"] != "ACCEPTED"
    assert store.get_intent(absent.job_id) is None
    assert store.get_result(absent.job_id) is None


def test_simultaneous_same_intent_launches_once(tmp_path: Path) -> None:
    barrier = threading.Barrier(2, timeout=5)
    local = threading.local()

    class BarrierStore(FleetJobStore):
        def get_intent(self, job_id: str) -> dict[str, object] | None:
            value = super().get_intent(job_id)
            local.calls = getattr(local, "calls", 0) + 1
            if local.calls == 2:
                barrier.wait()
            return value

    store = BarrierStore(tmp_path / "race.sqlite3")
    env = _envelope(tmp_path, "concurrent")
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    launches: list[object] = []

    class CountRemote(FakeRemote):
        def execute(self, **kwargs: object) -> dict[str, object]:
            launches.append(kwargs)
            return super().execute(**kwargs)

    def execute_once() -> str:
        return str(
            RemoteJobController(CountRemote(), store=store, require_intent=True).execute(
                env, now=NOW
            )["outcome"]
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute_once) for _ in range(2)]
        outcomes = [item.result(timeout=10) for item in futures]
    assert len(launches) == 1
    assert outcomes.count("EXECUTED") == 1


def test_reconcile_and_occupancy_keep_unknown_work(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "recover.sqlite3")
    env = _envelope(tmp_path, "unresolved")
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    store.mark_status(env.job_id, "RUNNING")
    recovered = store.reconcile_unresolved(
        env.job_id, reason="caller_supplied_without_absence_proof"
    )
    assert recovered["ok"] is False
    assert store.get_intent(env.job_id) is not None
    journal = FleetLifecycleJournal(tmp_path / "occupancy.sqlite3")
    journal.publish(
        dict(
            job_id="unknown-running-worker",
            host_id=env.host_id,
            lease_id="L",
            fence="F",
            status="UNKNOWN_OUTCOME",
            authority="fixture-controller",
        )
    )
    occupied = journal.occupancy(authority="arbitrary_nonempty_string")
    assert occupied["active_jobs"] != 0


def test_worker_cache_and_managed_path_do_not_false_accept(tmp_path: Path) -> None:
    workspace = tmp_path / "module-ws"
    workspace.mkdir()
    target = tmp_path / "cache_escape.json"
    data = dict(
        argv=["python", "fixture.py"],
        workspace=str(workspace),
        job_id="../../cache_escape",
        input_sha256="a" * 64,
    )
    with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "fixture", "")):
        run_envelope(data)
    assert target.is_file() is False
    path = r"C:\ProgramData\ProjectPipeline\worker_not_protected\job.py"
    verdict = classify_scheduled_action(
        runas="fixture_user", script_path=path, acl_fullcontrol_users=()
    )
    assert verdict["accepted_production_worker"] is False
    xml = (
        "<Task><Principals><Principal><UserId>fixture_user</UserId></Principal></Principals>"
        "<Actions><Exec><Command>C:\\ProgramData\\ProjectPipeline\\worker\\job.exe"
        "</Command></Exec></Actions></Task>"
    )
    classified = inspect_scheduled_task_xml(xml)
    assert classified["accepted_production_worker"] is False
    protocol_text = (
        SOURCE / "src/project_pipeline/autonomy_runtime/remote_worker_protocol.py"
    ).read_text(encoding="utf-8")
    assert "ssh_dispatch" not in protocol_text
    heartbeat = tmp_path / "managed_heartbeat.json"
    stop_flag = tmp_path / "managed.stop"
    pid_file = tmp_path / "managed.pid"
    code = run_managed_worker(
        [
            "--managed",
            "--heartbeat",
            str(heartbeat),
            "--stop-flag",
            str(stop_flag),
            "--pid-file",
            str(pid_file),
            "--max-seconds",
            "0.2",
        ]
    )
    assert code == 0
    payload = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["phase"] == "managed"
    assert payload["pid"]
    spaced = r"C:\Users\Windows 11\AppData\Local\Programs\Python\Python311\python.exe"
    quoted = owned_task_retirement_plan("ProjectPipelineFleetWorkerComfy", python_executable=spaced)
    assert quoted["ok"] is True
    tr = quoted["replacement_create_argv"][quoted["replacement_create_argv"].index("/TR") + 1]
    assert '"' in tr
    assert "--managed" in tr


def test_timeout_keeps_capacity_and_accept_uses_completion_clock(tmp_path: Path) -> None:
    workspace = tmp_path / "workflow"
    workspace.mkdir()
    admission = workspace / "admission.json"
    profile = MachineProfile(
        machine_id="COMFY-V4-CPU-01",
        hostname="COMFY-V4-CPU-01",
        role="CPU_WORKER",
        observed_at_utc=NOW,
        cpu_slots=8,
        memory_mb=32000,
        disk_mb=50000,
        principal="review_fixture_worker",
        observation_kind="MEASURED",
    )
    write_admission_record(
        admission,
        dict(
            c18_disposition="PM_ACCEPTED",
            reviewer_id="fixture-reviewer",
            implementer_id="fixture-implementer",
            source_sha=SHA,
            source_tree=TREE,
            hosts={
                profile.machine_id: dict(
                    state="READY",
                    freshness="fresh",
                    observation_kind="MEASURED",
                    observed_at_utc=NOW.isoformat(),
                    sid="S-1-5-21-comfy",
                    principal=profile.principal,
                    workspace_root=str(workspace),
                )
            },
        ),
    )
    with SchedulerStore(workspace / "scheduler.sqlite3", SOURCE) as scheduler:
        jobs = FleetJobStore(workspace / "jobs.sqlite3")
        journal = FleetLifecycleJournal(workspace / "journal.sqlite3")
        workflow = DispatchWorkflow(
            store=scheduler,
            jobs=jobs,
            profiles=(profile,),
            admission_path=admission,
            source_sha=SHA,
            source_tree=TREE,
            overlay_sha256="c" * 64,
            journal=journal,
        )

        class TimeoutRemote(FakeRemote):
            def execute(self, **_kwargs: object) -> dict[str, object]:
                return {"timed_out": True}

        returned = workflow.dispatch(
            task_id="PP-TASK-000516",
            holder_id="review-holder",
            argv=("python", "fixture.py"),
            workspace=str(workspace),
            workspace_root=str(tmp_path),
            principal=profile.principal,
            input_sha256="d" * 64,
            now=NOW,
            adapter=TimeoutRemote(),
        )
        leases = scheduler.list_active_leases(when=NOW)
        assert returned["outcome"] == "UNKNOWN_OUTCOME"
        assert leases
        completed_clock = NOW + timedelta(minutes=16)

        class AdvancedClock(datetime):
            @classmethod
            def now(cls, tz: object | None = None) -> datetime:
                del tz
                return completed_clock

        with patch.object(remote_job, "datetime", AdvancedClock):
            late = workflow.dispatch(
                task_id="PP-TASK-000519",
                holder_id="review-holder",
                argv=("python", "fixture.py"),
                workspace=str(workspace),
                workspace_root=str(tmp_path),
                principal=profile.principal,
                input_sha256="d" * 64,
                now=NOW,
                adapter=FakeRemote(),
            )
        assert late["outcome"] != "ACCEPTED"


def test_typeerror_after_launch_does_not_retry(tmp_path: Path) -> None:
    env = _envelope(tmp_path, "typeerror-retry")
    calls: list[object] = []

    class PartiallyExecuted(FakeRemote):
        def execute(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            if len(calls) == 1:
                raise TypeError("fixture failure after launch/side effect")
            return super().execute(**kwargs)

    result = RemoteJobController(PartiallyExecuted()).execute(env, now=NOW)
    assert len(calls) == 1
    assert result["outcome"] == "UNKNOWN_OUTCOME"


def test_useful_job_is_not_metadata_only_and_failed_loop_does_not_ok(
    tmp_path: Path,
) -> None:
    useful = runpy.run_path(str(SOURCE / "scripts" / "cycle20_useful_job.py"))
    artifact = tmp_path / "toy_useful_output.json"
    with contextlib.redirect_stdout(io.StringIO()):
        useful["run"](job_id="PP-TASK-000516", output=artifact)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert set(payload) != {"job_id", "artifact_sha256", "bytes"}
    assert payload["ok"] is True
    assert payload["verifier"] == "implementation_and_test_binding"
    assert payload["criterion_ids"]
    assert payload["implementation_paths"]
    assert payload.get("selected_source") != "remote_job.py"
    refused = tmp_path / "story_parent.json"
    with contextlib.redirect_stdout(io.StringIO()):
        useful["run"](job_id="PP-STORY-000065", output=refused)
    parent = json.loads(refused.read_text(encoding="utf-8"))
    assert parent["ok"] is False
    assert parent["reason"] == "structural_parent_not_selected_work"
    launches: list[str] = []

    def rejected_batch(**kwargs: object) -> dict[str, object]:
        ready = list(kwargs["ready"])  # type: ignore[arg-type]
        selected = ready[:2]
        launches.extend(selected)
        after = ready[2:]
        return dict(
            selected=selected,
            next_job=after[0] if after else None,
            results=[
                dict(task_id=item, outcome="REJECTED", reason="fixture_mandatory_failure")
                for item in selected
            ],
        )

    with patch.object(fleet_loop, "run_loop", side_effect=rejected_batch):
        result = fleet_loop.run_available_work(
            root=SOURCE,
            database=tmp_path / "unused.sqlite3",
            ready=["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"],
            blocked="PP-TASK-000518",
            profiles=(),
            adapter=FakeRemote(),
            workspace=tmp_path,
            workspace_root=tmp_path,
            source_sha=SHA,
            source_tree=TREE,
            overlay_sha256="c" * 64,
            principal="fixture",
            now=NOW,
        )
    assert result["ok"] is False
    assert launches != ["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"]
    structural = fleet_loop.run_available_work(
        root=SOURCE,
        database=tmp_path / "structural.sqlite3",
        ready=["PP-STORY-000065", "PP-STORY-000396"],
        blocked="PP-STORY-000139",
        profiles=(),
        adapter=FakeRemote(),
        workspace=tmp_path,
        workspace_root=tmp_path,
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        principal="fixture",
        now=NOW,
    )
    assert structural["ok"] is False
    assert structural["reason"] == "no_executable_leaf_ready"


def test_observation_evaluator_fails_when_hour_elapsed_without_recovery() -> None:
    fake = {
        "duration_met": True,
        "wall_seconds": 3600.0,
        "fault": {"recovered": True, "reconcile_reason": "no_intent", "killed": True},
        "source": {"sha": "75d6025476a52e577d36ecf8c16a45cf6b047551"},
        "heartbeats": [{"remaining_seconds": 1}] * 20,
        "completed_jobs": [{"results": [{"outcome": "ACCEPTED", "task_id": "PP-STORY-000065"}]}],
    }
    result = evaluate_observation(
        fake, expected_source_sha=SHA, require_useful_work=True, require_owned_recovery=True
    )
    assert result["ok"] is False
    assert any(
        token in " ".join(result["reasons"])
        for token in ("recovery", "source", "useful", "heartbeat", "no_intent")
    )


def test_observation_evaluator_requires_recovered_accepted_work_and_coverage() -> None:
    matching = {
        "duration_met": True,
        "wall_seconds": 3600.0,
        "fault": {
            "recovered": False,
            "killed": True,
            "owned_job_id": "C20-OWNED-FAULT",
            "intent_preserved": True,
            "reconcile_reason": "owned_worker_killed",
        },
        "source": {"sha": SHA},
        "heartbeats": [{"remaining_seconds": 1}] * 60,
        "completed_jobs": [{"results": [{"outcome": "EXECUTED", "task_id": "PP-TASK-000516"}]}],
    }
    failed = evaluate_observation(
        matching, expected_source_sha=SHA, require_useful_work=True, require_owned_recovery=True
    )
    assert failed["ok"] is False
    assert "recovery_not_proven" in failed["reasons"]
    assert "useful_work_missing" in failed["reasons"]
    matching["fault"]["recovered"] = True
    matching["completed_jobs"] = [
        {"results": [{"outcome": "ACCEPTED", "task_id": "PP-TASK-000516"}]}
    ]
    passed = evaluate_observation(
        matching, expected_source_sha=SHA, require_useful_work=True, require_owned_recovery=True
    )
    assert passed["ok"] is True


def test_kill_matches_running_ownership_before_result_cache(tmp_path: Path) -> None:
    workspace = tmp_path / "jobs"
    workspace.mkdir()
    own = workspace / ".pp_worker_results" / "C20-OWNED-FAULT.own.json"
    own.parent.mkdir()
    own.write_text(
        json.dumps(
            {
                "job_id": "C20-OWNED-FAULT",
                "fence": "owned-fault-1",
                "principal": "fixture",
                "pid": 424242,
                "child_pid": 0,
                "phase": "RUNNING",
            }
        ),
        encoding="utf-8",
    )
    kill_calls: list[list[str]] = []

    def fake_kill(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        kill_calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    with patch("subprocess.run", side_effect=fake_kill):
        result = run_envelope(
            {
                "action": "kill",
                "pid": 424242,
                "job_id": "C20-OWNED-FAULT",
                "fence": "owned-fault-1",
                "principal": "fixture",
                "workspace": str(workspace),
            }
        )
    if os.name != "nt":
        assert result["ok"] is False
        assert result.get("reason") == "kill_unsupported"
    else:
        assert result["ok"] is True
        assert kill_calls
    missing = run_envelope(
        {
            "action": "kill",
            "pid": 424242,
            "job_id": "OTHER-JOB",
            "fence": "owned-fault-1",
            "principal": "fixture",
            "workspace": str(workspace),
        }
    )
    assert missing.get("reason") == "unowned_pid"


def test_prelaunch_reject_releases_dispatched_claim(tmp_path: Path) -> None:
    store = FleetJobStore(tmp_path / "prelaunch.sqlite3")
    env = _envelope(tmp_path, "prelaunch", host_id="WIN-EVSH1DN8H5O")
    store.persist_intent(env.model_dump(mode="json"), now=NOW)
    controller = RemoteJobController(
        FakeRemote(),
        store=store,
        require_intent=True,
        expected_source_sha=SHA,
        expected_source_tree=TREE,
    )
    first = controller.execute(env, now=NOW)
    assert first["outcome"] == "REJECTED"
    assert first["reason"] == "wrong_host"
    intent = store.get_intent(env.job_id)
    assert intent is not None
    assert intent["status"] == "INTENT"
    second = controller.execute(env, now=NOW)
    assert second["reason"] == "wrong_host"
    assert second["reason"] != "unresolved_in_flight"


def test_retirement_remote_keeps_tr_as_one_token() -> None:
    spaced = r"C:\Users\Windows 11\AppData\Local\Programs\Python\Python311\python.exe"
    plan = owned_task_retirement_plan("ProjectPipelineFleetWorkerComfy", python_executable=spaced)
    argv = [str(item) for item in plan["replacement_create_argv"]]
    remote = quote_command(argv)
    after_tr = remote.split("/TR", 1)[1]
    before_f = after_tr.split("/F", 1)[0]
    assert "--managed" in before_f
    assert before_f.count('"') >= 2
    assert remote.index("--managed") < remote.index("/F")


def test_instruction_manifest_hashes_follow_resolved_public_bytes(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay"
    source = tmp_path / "source"
    managed = Path("scripts/validate_instructions.py")
    (overlay / "instructions").mkdir(parents=True)
    (source / "scripts").mkdir(parents=True)
    (source / managed).write_text("public-bytes", encoding="utf-8")
    stale = {
        "files": [
            {
                "path": managed.as_posix(),
                "sha256": "0" * 64,
                "size_bytes": 1,
            }
        ]
    }
    (overlay / "instructions" / "INSTRUCTION_MANIFEST.json").write_text(
        json.dumps(stale), encoding="utf-8"
    )
    refresh_instruction_manifest_hashes(overlay, source)
    updated = json.loads((overlay / "instructions" / "INSTRUCTION_MANIFEST.json").read_text())
    body = (source / managed).read_bytes()
    assert updated["files"][0]["sha256"] == hashlib.sha256(body).hexdigest()
    assert updated["files"][0]["size_bytes"] == len(body)
