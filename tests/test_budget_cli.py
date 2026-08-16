import json
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.domain.budget import BudgetLimit, BudgetScopeType, budget_identifier


def _limit(path: Path, cap: int = 1_000_000) -> Path:
    model = BudgetLimit(
        limit_id=budget_identifier("LIMIT", "GLOBAL:*", "cli"),
        scope_type=BudgetScopeType.GLOBAL,
        scope_id="*",
        cycle_id="cli",
        hard_cap_microunits=cap,
        soft_cap_microunits=cap,
    )
    path.write_text(json.dumps(model.model_dump(mode="json")), encoding="utf-8")
    return path


def test_budget_cli_status_is_machine_readable(project_root, tmp_path, capsys):
    db = tmp_path / "budget.sqlite"
    assert main(["budget", "status", "--root", str(project_root), "--database", str(db)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["budget"]["project_id"] == "PROJECT-PIPELINE"


def test_budget_cli_limit_requires_explicit_approval(project_root, tmp_path, capsys):
    db = tmp_path / "budget.sqlite"
    limit = _limit(tmp_path / "limit.json")
    code = main(
        [
            "budget",
            "limit",
            "--root",
            str(project_root),
            "--database",
            str(db),
            "--limit",
            str(limit),
        ]
    )
    assert code != 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "configuration_invalid"
    assert "--apply and --approve" in payload["message"]


def test_budget_cli_anomaly_is_approval_gated_and_persists(project_root, tmp_path, capsys):
    db = tmp_path / "budget.sqlite"
    base = [
        "budget",
        "anomaly",
        "--root",
        str(project_root),
        "--database",
        str(db),
        "--expected-p90-microunits",
        "100000",
        "--observed-microunits",
        "260000",
    ]
    assert main(base) != 0
    capsys.readouterr()
    assert main([*base, "--apply", "--approve"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["anomaly"]["severity"] == "BLOCK"
    assert payload["anomaly"]["block_new_paid_work"] is True


def test_budget_cli_impact_is_read_only_analysis(project_root, tmp_path, capsys):
    db = tmp_path / "budget.sqlite"
    old = _limit(tmp_path / "old.json", 1_000_000)
    new = _limit(tmp_path / "new.json", 700_000)
    assert (
        main(
            [
                "budget",
                "impact",
                "--root",
                str(project_root),
                "--database",
                str(db),
                "--old-limit",
                str(old),
                "--limit",
                str(new),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["impact"]["old_hard_cap_microunits"] == 1_000_000
    assert payload["impact"]["new_hard_cap_microunits"] == 700_000
