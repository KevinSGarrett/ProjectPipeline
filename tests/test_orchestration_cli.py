import json
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.domain.orchestration import (
    WorkflowDefinition,
    WorkflowStepDefinition,
    orchestration_identifier,
)


def _definition_file(tmp_path: Path) -> tuple[WorkflowDefinition, Path]:
    definition = WorkflowDefinition(
        definition_id=orchestration_identifier("workflow_definition", "cli-build", "1"),
        workflow_name="cli-build",
        version="1",
        steps=(WorkflowStepDefinition(step_id="run", name="Run"),),
    )
    path = tmp_path / "definition.json"
    path.write_text(json.dumps(definition.model_dump(mode="json")), encoding="utf-8")
    return definition, path


def test_orchestration_cli_backend_status_is_truthful(project_root, capsys):
    assert main(["orchestration", "backend-status", "--root", str(project_root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["live_external_qualification_claimed"] is False
    states = {item["backend"]: item["qualification"] for item in payload["backends"]}
    assert states["MOCK"] == "LOCAL_VERIFIED"
    assert states["HATCHET"] != "LIVE_VERIFIED"


def test_orchestration_cli_status_and_recover_do_not_require_workflow_id(
    project_root, tmp_path, capsys
):
    db = tmp_path / "orchestration.sqlite"
    assert (
        main(["orchestration", "status", "--root", str(project_root), "--database", str(db)]) == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["orchestration"]["workflows"] == 0
    assert (
        main(
            [
                "orchestration",
                "recover",
                "--root",
                str(project_root),
                "--database",
                str(db),
                "--apply",
                "--approve",
            ]
        )
        == 0
    )
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["stale_worker_decisions"] == []
    assert recovered["unknown_outcome_decisions"] == []


def test_orchestration_cli_register_requires_approval(project_root, tmp_path, capsys):
    _, definition_path = _definition_file(tmp_path)
    db = tmp_path / "orchestration.sqlite"
    assert (
        main(
            [
                "orchestration",
                "register",
                "--root",
                str(project_root),
                "--database",
                str(db),
                "--definition",
                str(definition_path),
            ]
        )
        != 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "configuration_invalid"
    assert "--apply and --approve" in payload["message"]


def test_orchestration_cli_register_start_query_local_reference(project_root, tmp_path, capsys):
    definition, definition_path = _definition_file(tmp_path)
    db = tmp_path / "orchestration.sqlite"
    base = ["--root", str(project_root), "--database", str(db), "--apply", "--approve"]
    assert main(["orchestration", "register", *base, "--definition", str(definition_path)]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "orchestration",
                "start",
                *base,
                "--definition-id",
                definition.definition_id,
                "--idempotency-key",
                "cli-idem",
                "--backend",
                "LOCAL_REFERENCE",
            ]
        )
        == 0
    )
    started = json.loads(capsys.readouterr().out)
    workflow_id = started["workflow"]["workflow_id"]
    assert started["workflow"]["state"] == "RUNNING"
    assert (
        main(
            [
                "orchestration",
                "query",
                "--root",
                str(project_root),
                "--database",
                str(db),
                "--workflow-id",
                workflow_id,
            ]
        )
        == 0
    )
    queried = json.loads(capsys.readouterr().out)
    assert queried["workflow"]["workflow_id"] == workflow_id


def test_orchestration_cli_simulates_unknown_outcome(project_root, capsys):
    assert (
        main(
            [
                "orchestration",
                "simulate",
                "--root",
                str(project_root),
                "--scenario",
                "unknown-outcome",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["simulation"]["passed"] is True
    assert payload["simulation"]["scenario"] == "unknown-outcome"
