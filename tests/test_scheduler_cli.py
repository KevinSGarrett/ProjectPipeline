from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.cli import main

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
    assert plan["candidate_count"] > 0
    assert 0 < len(plan["lanes"]) <= 4
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
    task_id = plan["lanes"][0]["task_id"]
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
    task_id = plan["lanes"][0]["task_id"]

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


def test_scheduler_takeover_governor_scopes_privacy_blocks_to_lane(tmp_path: Path, capsys) -> None:
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
    governor = result["takeover_governor"]
    lane_matrix = governor["lane_matrix"]
    assert lane_matrix
    assert any(
        row["state"] == "ACTIVE" and not row.get("requires_privacy_attestation", False)
        for row in lane_matrix
    )
    for row in lane_matrix:
        if row.get("requires_privacy_attestation", False):
            assert row["state"] in {"HUMAN_REQUIRED", "BLOCKED"}
    assert governor["global_stop_required"] is False
