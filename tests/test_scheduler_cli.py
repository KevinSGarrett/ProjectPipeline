from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.domain.scheduler import AccessMode, ResourceClaim, ResourceType
from project_pipeline.scheduler.persistence import SchedulerStore

ROOT = Path(__file__).resolve().parents[1]


def normal_signals(tmp_path: Path) -> Path:
    path = tmp_path / "normal-signals.json"
    path.write_text(json.dumps({"schema_version": "1.0.0", "queue_depth": 0}), encoding="utf-8")
    return path


def test_scheduler_plan_is_machine_readable_and_dry_run(tmp_path: Path, capsys) -> None:
    db = tmp_path / "scheduler.db"
    signals = normal_signals(tmp_path)
    assert (
        main(
            [
                "scheduler",
                "plan",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "4",
                "--signals-file",
                str(signals),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] is True
    plan = result["plan"]
    assert plan["candidate_count"] >= 0
    assert len(plan["lanes"]) <= 4
    assert plan["selection_method"]
    assert result["control_snapshot_id"] == plan["control_snapshot_id"]


def test_scheduler_acquire_requires_explicit_apply_and_approval(tmp_path: Path, capsys) -> None:
    db = tmp_path / "scheduler.db"
    signals = normal_signals(tmp_path)
    assert (
        main(
            [
                "scheduler",
                "plan",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "1",
                "--signals-file",
                str(signals),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)["plan"]
    task_id = plan["lanes"][0]["task_id"] if plan["lanes"] else "PP-TASK-000380"
    code = main(
        [
            "scheduler",
            "acquire",
            "--root",
            str(ROOT),
            "--database",
            str(db),
            "--task-id",
            task_id,
            "--signals-file",
            str(signals),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["ok"] is False
    assert "requires both --apply and --approve" in result["message"]


def test_scheduler_acquire_and_release_are_fenced(tmp_path: Path, capsys) -> None:
    db = tmp_path / "scheduler.db"
    signals = normal_signals(tmp_path)
    assert (
        main(
            [
                "scheduler",
                "plan",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "1",
                "--signals-file",
                str(signals),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)["plan"]
    task_id = plan["lanes"][0]["task_id"] if plan["lanes"] else "PP-TASK-000380"
    with SchedulerStore(db, ROOT) as store:
        store.ensure_local_pools()
        seed = store.acquire_bundle(
            task_id=task_id,
            holder_id="actor:test",
            claims=(
                ResourceClaim(
                    resource_key="src/project_pipeline/cli.py",
                    resource_type=ResourceType.PATH,
                    access_mode=AccessMode.EXCLUSIVE,
                ),
            ),
            ttl_seconds=60,
        )
        assert seed.acquired
        for item in seed.leases:
            store.release_lease(
                item.lease_id, holder_id="actor:test", fencing_token=item.fencing_token
            )

    assert (
        main(
            [
                "scheduler",
                "acquire",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "1",
                "--task-id",
                task_id,
                "--holder-id",
                "actor:test",
                "--signals-file",
                str(signals),
                "--apply",
                "--approve",
            ]
        )
        == 0
    )
    acquired = json.loads(capsys.readouterr().out)["lease_bundle"]
    assert acquired["acquired"] is True
    assert acquired["leases"]
    lease = acquired["leases"][0]

    assert (
        main(
            [
                "scheduler",
                "release",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--lease-id",
                lease["lease_id"],
                "--holder-id",
                "actor:test",
                "--fencing-token",
                str(lease["fencing_token"]),
                "--apply",
                "--approve",
            ]
        )
        == 0
    )
    released = json.loads(capsys.readouterr().out)["lease"]
    assert released["released_at_utc"] is not None


def test_scheduler_simulation_exercises_backpressure_modes(tmp_path: Path, capsys) -> None:
    db = tmp_path / "scheduler.db"
    assert (
        main(
            [
                "scheduler",
                "simulate",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "4",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    simulations = result["simulations"]
    assert [item["scenario_name"] for item in simulations] == [
        "normal",
        "congested",
        "brownout",
        "halt",
    ]
    by_name = {item["scenario_name"]: item for item in simulations}
    assert by_name["normal"]["plan"]["backpressure"]["admit_new_work"] is True
    assert by_name["brownout"]["plan"]["backpressure"]["admit_new_work"] is False
    assert by_name["halt"]["plan"]["backpressure"]["admit_new_work"] is False
    assert by_name["brownout"]["plan"]["lanes"] == []
    assert by_name["halt"]["plan"]["lanes"] == []


def test_scheduler_acquire_recovers_owned_in_progress_task(tmp_path: Path, capsys) -> None:
    db = tmp_path / "scheduler.db"
    signals = normal_signals(tmp_path)
    with SchedulerStore(db, ROOT) as store:
        store.ensure_local_pools()
        seed = store.acquire_bundle(
            task_id="PP-TASK-000380",
            holder_id="cursor-combined-agent",
            claims=(
                ResourceClaim(
                    resource_key="src/project_pipeline/cli.py",
                    resource_type=ResourceType.PATH,
                    access_mode=AccessMode.EXCLUSIVE,
                ),
            ),
            ttl_seconds=60,
        )
        assert seed.acquired
        for lease in seed.leases:
            store.release_lease(
                lease.lease_id,
                holder_id="cursor-combined-agent",
                fencing_token=lease.fencing_token,
            )

    assert (
        main(
            [
                "scheduler",
                "acquire",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "1",
                "--task-id",
                "PP-TASK-000380",
                "--holder-id",
                "cursor-combined-agent",
                "--signals-file",
                str(signals),
                "--apply",
                "--approve",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["recovered_in_progress_task"] is True
    assert result["lease_bundle"]["acquired"] is True


def test_scheduler_acquire_recovers_claims_from_task_metadata(tmp_path: Path, capsys) -> None:
    db = tmp_path / "scheduler.db"
    signals = normal_signals(tmp_path)
    assert (
        main(
            [
                "scheduler",
                "acquire",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "1",
                "--task-id",
                "PP-TASK-000380",
                "--holder-id",
                "cursor-combined-agent",
                "--signals-file",
                str(signals),
                "--apply",
                "--approve",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["recovered_in_progress_task"] is True
    assert result["lease_bundle"]["acquired"] is True
    assert result["lease_bundle"]["leases"]


def test_scheduler_plan_omits_takeover_governor(tmp_path: Path, capsys) -> None:
    db = tmp_path / "scheduler.db"
    signals = normal_signals(tmp_path)
    assert (
        main(
            [
                "scheduler",
                "plan",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--max-lanes",
                "1",
                "--signals-file",
                str(signals),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert "takeover_governor" not in result
