from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.autonomy_runtime.fleet_loop import (
    build_parser,
    run_loop,
    select_two_useful_jobs,
    useful_argv,
)
from project_pipeline.autonomy_runtime.lifecycle import FleetLifecycleJournal
from project_pipeline.autonomy_runtime.service import LocalSubprocessDispatchAdapter
from project_pipeline.scheduler.admission import write_admission_record
from project_pipeline.scheduler.fleet import MachineProfile

NOW = datetime(2026, 9, 8, tzinfo=UTC)
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


def test_selects_two_jobs_and_preserves_blocked_lane() -> None:
    jobs = select_two_useful_jobs(
        ["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000518"],
        blocked="PP-TASK-000518",
    )
    assert jobs["selected"] == ["PP-TASK-000516", "PP-TASK-000517"]
    assert jobs["blocked"] == "PP-TASK-000518"


def test_loop_dispatches_local_adapter_and_continues(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    admission = database.with_name("fleet_admission.json")
    write_admission_record(
        admission,
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
                }
            },
        },
    )
    adapter = LocalSubprocessDispatchAdapter()
    result = run_loop(
        root=ROOT,
        database=database,
        ready=["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"],
        blocked="PP-TASK-000518",
        profiles=(_profile(),),
        adapter=adapter,
        workspace=workspace,
        workspace_root=tmp_path,
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        principal=r"win-evsh1dn8h5o\kines",
        now=NOW,
    )
    assert result["selected"] == ["PP-TASK-000516", "PP-TASK-000517"]
    assert result["next_job"] == "PP-TASK-000519"
    assert result["blocked"] == "PP-TASK-000518"
    assert all(item.get("outcome") == "ACCEPTED" for item in result["results"])


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
    assert argv[1].endswith("cycle20_useful_job.py")
    assert "PP-TASK-000384" not in argv
