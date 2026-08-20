from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.jira import load_issues

ROOT = Path(__file__).resolve().parents[1]


def test_control_sequence_and_status_are_machine_readable(tmp_path: Path, capsys) -> None:
    db = tmp_path / "control.db"
    assert main(["control", "sequence", "--root", str(ROOT), "--database", str(db)]) == 0
    sequence = json.loads(capsys.readouterr().out)
    assert sequence["sequence"]["task_count"] == len(load_issues(ROOT))
    assert sequence["control_status"]["snapshot_count"] == 1
    assert main(["control", "status", "--root", str(ROOT), "--database", str(db)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["control"]["latest_snapshot_id"]


def test_ready_plan_is_dry_run(tmp_path: Path, capsys) -> None:
    db = tmp_path / "control.db"
    assert main(["control", "ready-plan", "--root", str(ROOT), "--database", str(db)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] is True
    operations = result["operations"]
    assert isinstance(operations, list)
    ready_ids = {item["task_id"] for item in operations}
    assert "PP-TASK-000385" not in ready_ids
    assert all(item["next_state"] == "READY" for item in operations)


def test_ready_plan_can_target_one_task(tmp_path: Path, capsys) -> None:
    db = tmp_path / "control.db"
    assert (
        main(
            [
                "control",
                "ready-plan",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--task-id",
                "PP-TASK-000381",
            ]
        )
        == 0
    )
    targeted = json.loads(capsys.readouterr().out)
    assert targeted["operations"] == []


def test_ready_apply_can_target_one_task(tmp_path: Path, capsys) -> None:
    db = tmp_path / "control.db"
    assert main(["control", "ready-plan", "--root", str(ROOT), "--database", str(db)]) == 0
    planned = json.loads(capsys.readouterr().out)
    if not planned["operations"]:
        return
    target = planned["operations"][0]["task_id"]
    assert target != "PP-TASK-000385"
    assert (
        main(
            [
                "control",
                "ready-apply",
                "--root",
                str(ROOT),
                "--database",
                str(db),
                "--task-id",
                target,
                "--apply",
                "--approve",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["applied_transition_count"] == 1
    assert {item["task_id"] for item in result["applied_transitions"]} == {target}


def test_ready_apply_requires_explicit_apply_and_approval(tmp_path: Path, capsys) -> None:
    db = tmp_path / "control.db"
    code = main(["control", "ready-apply", "--root", str(ROOT), "--database", str(db)])
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["ok"] is False
    assert "requires both --apply and --approve" in result["message"]


def test_ready_apply_transitions_only_currently_ready_backlog(tmp_path: Path, capsys) -> None:
    db = tmp_path / "control.db"
    code = main(
        [
            "control",
            "ready-apply",
            "--root",
            str(ROOT),
            "--database",
            str(db),
            "--apply",
            "--approve",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    applied_ids = {item["task_id"] for item in result["applied_transitions"]}
    assert "PP-TASK-000385" not in applied_ids
    assert result["applied_transition_count"] == len(applied_ids)
    leftover = main(["control", "ready-plan", "--root", str(ROOT), "--database", str(db)])
    assert leftover == 0
    remaining = json.loads(capsys.readouterr().out)
    assert remaining["operations"] == []


def test_cli_has_no_takeover_writer_command() -> None:
    from project_pipeline.cli import build_parser

    parser = build_parser()
    subparsers = next(
        action for action in parser._subparsers._group_actions if action.choices is not None
    )
    assert "takeover" not in subparsers.choices
    assert not (ROOT / "src/project_pipeline/lifecycle/takeover_cli.py").exists()


def test_control_evaluate_omits_takeover_governor(tmp_path: Path, capsys) -> None:
    db = tmp_path / "control.db"
    assert main(["control", "evaluate", "--root", str(ROOT), "--database", str(db)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "takeover_governor" not in result
