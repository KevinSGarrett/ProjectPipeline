from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.autonomy_runtime.dispatch_workflow import DispatchWorkflow
from project_pipeline.autonomy_runtime.durable_jobs import FleetJobStore
from project_pipeline.autonomy_runtime.fleet_loop import (
    _sidecar_path,
    build_parser,
    choose_measured_worker,
    duplicate_work_audit,
    run_available_work,
    run_loop,
    select_two_useful_jobs,
    useful_argv,
)
from project_pipeline.autonomy_runtime.lifecycle import FleetLifecycleJournal
from project_pipeline.overlay import locate_input
from project_pipeline.scheduler.admission import write_admission_record
from project_pipeline.scheduler.fleet import MachineProfile
from project_pipeline.scheduler.persistence import SchedulerStore

NOW = datetime.now(UTC)
SHA = "a" * 40
TREE = "b" * 40
ROOT = Path(__file__).resolve().parents[3]


def _profile() -> MachineProfile:
    return MachineProfile.model_validate(
        {
            "machine_id": "WIN-EVSH1DN8H5O",
            "hostname": "WIN-EVSH1DN8H5O",
            "role": "MEMORY_HEAVY_BATCH_WORKER",
            "observed_at_utc": NOW,
            "isa_flags": ("avx",),
            "cpu_slots": 8,
            "memory_mb": 64000,
            "disk_mb": 70000,
            "principal": r"win-evsh1dn8h5o\kines",
            "observation_kind": "MEASURED",
        }
    )


def _write_xeon_admission(path: Path) -> None:
    write_admission_record(
        path,
        {
            "c18_disposition": "PM_ACCEPTED",
            "reviewer_id": "rev",
            "implementer_id": "impl",
            "source_sha": SHA,
            "source_tree": TREE,
            "hosts": {
                "WIN-EVSH1DN8H5O": {
                    "state": "READY",
                    "freshness": "fresh",
                    "observation_kind": "MEASURED",
                    "observed_at_utc": NOW.isoformat(),
                    "sid": "S-1-5-21-xeon",
                    "principal": r"win-evsh1dn8h5o\kines",
                    "workspace_root": r"C:\Users\kines\ProjectPipeline\jobs",
                }
            },
        },
    )


def _run_kwargs(tmp_path: Path) -> dict[str, object]:
    database = tmp_path / "state.sqlite3"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_xeon_admission(_sidecar_path(database, "fleet_admission.json"))
    return {
        "root": ROOT,
        "database": database,
        "blocked": "PP-TASK-000518",
        "profiles": (_profile(),),
        "adapter": _RemoteAdapter(),
        "workspace": workspace,
        "workspace_root": tmp_path,
        "source_sha": SHA,
        "source_tree": TREE,
        "overlay_sha256": "c" * 64,
        "principal": r"win-evsh1dn8h5o\kines",
        "now": NOW,
    }


class _RemoteAdapter:
    remote_host = True
    machine_id = "WIN-EVSH1DN8H5O"
    _junit = (
        b"<testsuite tests='1' failures='0' errors='0' skipped='0'>"
        b"<testcase classname='cycle21' name='native_pass'/></testsuite>"
    )

    def execute(self, **_kwargs: object) -> dict[str, object]:
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout_sha256": "1" * 64,
            "stderr_sha256": "2" * 64,
            "payload_sha256": "3" * 64,
            "remote_pid": "4242",
            "context_consumption": {
                "ok": True,
                "worker_id": "WIN-EVSH1DN8H5O:4242",
                "status": "CONSUMED",
            },
        }

    def acquire_workspace_file(
        self, working_directory: Path, name: str, dest: Path
    ) -> bytes | None:
        del working_directory
        if name != "junit.xml":
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self._junit)
        return self._junit


def test_selects_two_jobs_and_preserves_blocked_lane() -> None:
    jobs = select_two_useful_jobs(
        ["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000518"],
        blocked="PP-TASK-000518",
    )
    assert jobs["selected"] == ["PP-TASK-000516", "PP-TASK-000517"]
    assert jobs["blocked"] == "PP-TASK-000518"


def test_select_skips_structural_parents() -> None:
    jobs = select_two_useful_jobs(
        ["PP-STORY-000065", "PP-TASK-000516", "PP-TASK-000517"],
        blocked="PP-STORY-000139",
    )
    assert jobs["selected"] == ["PP-TASK-000516", "PP-TASK-000517"]
    assert "PP-STORY-000065" in jobs["skipped_structural"]


def test_loop_dispatches_local_adapter_and_continues(tmp_path: Path) -> None:
    result = run_loop(
        ready=["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"],
        **_run_kwargs(tmp_path),
    )
    assert result["selected"] == ["PP-TASK-000516", "PP-TASK-000517"]
    assert result["next_job"] == "PP-TASK-000519"
    assert result["blocked"] == "PP-TASK-000518"
    assert all(item.get("outcome") == "ACCEPTED" for item in result["results"])


def test_available_work_dispatches_next_job_after_first_pair(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    result = run_available_work(
        ready=["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"],
        **kwargs,
    )
    assert result["ok"] is True
    assert result["selected"] == ["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"]
    assert len(result["completed_jobs"]) == 2
    empty = run_available_work(ready=[], **kwargs)
    assert empty["ok"] is False
    assert empty["reason"] == "director_ready_empty"


def test_unknown_machine_id_does_not_widen_to_all_hosts(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    _write_xeon_admission(database.with_name("fleet_admission.json"))
    with SchedulerStore(database, ROOT) as store:
        workflow = DispatchWorkflow(
            store=store,
            jobs=FleetJobStore(database.with_name("fleet_jobs.sqlite3")),
            profiles=(_profile(),),
            admission_path=database.with_name("fleet_admission.json"),
            source_sha=SHA,
            source_tree=TREE,
            overlay_sha256="c" * 64,
        )
        result = workflow.dispatch(
            task_id="PP-TASK-000516",
            holder_id="actor:test",
            argv=("python", "-c", "print(1)"),
            workspace=str(tmp_path),
            workspace_root=str(tmp_path),
            principal=r"win-evsh1dn8h5o\kines",
            input_sha256="d" * 64,
            now=NOW,
            machine_id="NO-SUCH-HOST",
        )
    assert result["outcome"] == "REJECTED"
    assert result["reason"] == "unknown_machine"


def test_lifecycle_journal_zero_occupancy_requires_authority(tmp_path: Path) -> None:
    journal = FleetLifecycleJournal(tmp_path / "life.sqlite3")
    empty = journal.occupancy(authority="lease-store")
    assert empty["active_jobs"] == 0
    assert empty["absence_authority"] == "lease-store"
    journal.publish(
        {
            "job_id": "PP-TASK-000516",
            "host_id": "WIN-EVSH1DN8H5O",
            "lease_id": "LEASE-AAAAAAAAAAAAAAAAAAAA",
            "fence": "1",
            "status": "DISPATCHED",
        }
    )
    occupied = journal.occupancy(authority="lease-store")
    assert occupied["active_jobs"] == 1
    journal.publish(
        {
            "job_id": "PP-TASK-000516",
            "host_id": "WIN-EVSH1DN8H5O",
            "lease_id": "LEASE-AAAAAAAAAAAAAAAAAAAA",
            "fence": "1",
            "status": "UNKNOWN_OUTCOME",
        }
    )
    rows = journal.snapshot()
    assert rows[0]["status"] == "UNKNOWN_OUTCOME"


def test_cli_discovers_fleet_loop() -> None:
    parser = build_parser()
    args = parser.parse_args(["status", "--duration-seconds", "3600", "--live-ssh"])
    assert args.action == "status"
    assert args.duration_seconds == 3600
    assert args.live_ssh is True


def test_lifecycle_has_no_kill_or_recover() -> None:
    assert not hasattr(FleetLifecycleJournal, "kill")
    assert not hasattr(FleetLifecycleJournal, "recover_worker")


def test_useful_job_writes_artifact(tmp_path: Path) -> None:
    argv = useful_argv(ROOT, "PP-TASK-000516")
    assert argv[1].endswith("cycle21_validation_job.py")
    assert "PP-TASK-000384" not in argv


def test_duplicate_work_audit_and_structural_ready_fail_closed() -> None:
    audit = duplicate_work_audit(ROOT)
    catalog = locate_input(ROOT, "plans/_traceability/requirements.jsonl")
    if catalog.is_file():
        assert "REQ-CTRL-0004" in audit["incomplete_requirements"]
        assert any(
            item.get("issue_id") == "PP-TASK-000381"
            and "REQ-CTRL-0004" in item.get("requirement_ids", [])
            for item in audit["findings"]
        )
    else:
        assert audit["incomplete_requirements"] == []
        assert audit["findings"] == []
    empty = select_two_useful_jobs(
        ["PP-STORY-000065", "PP-STORY-000396"], blocked="PP-STORY-000139"
    )
    assert empty["selected"] == []
    assert empty["skipped_structural"] == ["PP-STORY-000065", "PP-STORY-000396"]


def test_choose_measured_worker_prefers_xeon_and_falls_back_to_comfy() -> None:
    xeon = _profile().model_copy(update={"sid": None, "observation_kind": "PARTIAL"})
    comfy = MachineProfile.model_validate(
        {
            "machine_id": "COMFY-V4-CPU-01",
            "hostname": "COMFY-V4-CPU-01",
            "role": "CPU_WORKER",
            "observed_at_utc": NOW,
            "isa_flags": ("avx", "avx2"),
            "cpu_slots": 8,
            "memory_mb": 32000,
            "disk_mb": 22000,
            "principal": r"comfy-v4-cpu-01\windows 11",
            "observation_kind": "MEASURED",
            "sid": "S-1-5-21-comfy",
        }
    )
    chosen = choose_measured_worker((xeon, comfy))
    assert chosen is not None
    assert chosen.machine_id == "COMFY-V4-CPU-01"
    xeon_ready = _profile().model_copy(update={"sid": "S-1-5-21-xeon"})
    preferred = choose_measured_worker((xeon_ready, comfy))
    assert preferred is not None
    assert preferred.machine_id == "WIN-EVSH1DN8H5O"
