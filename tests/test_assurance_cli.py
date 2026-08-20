import json
from datetime import UTC, datetime

from project_pipeline.cli import main
from project_pipeline.domain.assurance import (
    ScopeContract,
    assurance_fingerprint,
    assurance_identifier,
)


def test_assurance_cli_status_initializes_ppdb_0012(project_root, tmp_path, capsys):
    db = tmp_path / "assurance.sqlite"
    assert main(["assurance", "status", "--root", str(project_root), "--database", str(db)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["assurance"]["gate_evaluations"] == 0


def test_assurance_cli_compile_is_dry_run_by_default(project_root, tmp_path, capsys):
    db = tmp_path / "assurance.sqlite"
    assert main(["assurance", "compile", "--root", str(project_root), "--database", str(db)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "DRY_RUN"
    assert payload["verification_plan"]["criteria"]


def test_assurance_cli_record_requires_apply_and_approve(project_root, tmp_path, capsys):
    db = tmp_path / "assurance.sqlite"
    code = main(
        ["assurance", "compile", "--root", str(project_root), "--database", str(db), "--record"]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "configuration_invalid"
    assert "--apply and --approve" in payload["message"]


def test_assurance_cli_completion_gate_truthfully_reports_not_complete(
    project_root, tmp_path, capsys
):
    db = tmp_path / "assurance.sqlite"
    code = main(
        ["assurance", "completion-gate", "--root", str(project_root), "--database", str(db)]
    )
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["completion_gate"]["state"] == "NOT_COMPLETE"
    assert payload["completion_gate"]["final_complete"] is False
    failed = {
        item["question_number"]
        for item in payload["completion_gate"]["questions"]
        if not item["passed"]
    }
    assert failed == {2, 5, 16}
    golden = next(
        item for item in payload["completion_gate"]["questions"] if item["question_number"] == 5
    )
    assert "EVID-000116" in golden["evidence_ids"]
    command_center = next(
        item for item in payload["completion_gate"]["questions"] if item["question_number"] == 13
    )
    assert command_center["passed"] is True


def test_assurance_cli_candidate_challenges_lazy_completion(project_root, tmp_path, capsys):
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "work_item_id": "PP-TASK-X",
                "implementer_id": "worker-a",
                "criteria_total": 3,
                "criteria_passing": 2,
                "stale_evidence_count": 1,
                "unknown_count": 0,
                "independent_review_required": True,
                "independent_review_satisfied": False,
            }
        ),
        encoding="utf-8",
    )
    assert main(["assurance", "candidate", "--root", str(project_root), "--input", str(path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["candidate_completion"]["state"] == "CHALLENGE"


def test_assurance_cli_scope_change_record_is_approval_gated(project_root, tmp_path, capsys):
    db = tmp_path / "assurance.sqlite"
    scope = ScopeContract(
        scope_id=assurance_identifier("SCOPE", "PP-TASK-X", "cli"),
        work_item_id="PP-TASK-X",
        included_behavior=("assurance",),
        excluded_behavior=("unrelated",),
        allowed_paths=("src/project_pipeline/assurance",),
        escalation_conditions=("outside scope",),
        frozen_criteria_fingerprint=assurance_fingerprint("criteria"),
        frozen_at_utc=datetime(2026, 8, 15, tzinfo=UTC),
    )
    path = tmp_path / "scope.json"
    path.write_text(scope.model_dump_json(), encoding="utf-8")
    base = [
        "assurance",
        "scope-change",
        "--root",
        str(project_root),
        "--database",
        str(db),
        "--scope",
        str(path),
        "--requested-behavior",
        "new behavior",
        "--record",
    ]
    assert main(base) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "--apply and --approve" in payload["message"]


def test_assurance_cli_simulation_is_machine_readable(project_root, capsys):
    assert (
        main(["assurance", "simulate", "--root", str(project_root), "--scenario", "attempt_loop"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["assurance_simulation"]["passed"] is True
