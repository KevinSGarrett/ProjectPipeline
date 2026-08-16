import json

from project_pipeline.cli import main


def test_verification_cli_status_initializes_ppdb_0013(project_root, tmp_path, capsys):
    db = tmp_path / "verification.sqlite"
    assert main(["verification", "status", "--root", str(project_root), "--database", str(db)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verification"]["run_count"] == 0


def test_verification_cli_tools_is_machine_readable(project_root, capsys):
    assert main(["verification", "tools", "--root", str(project_root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["verification_tools"]) == 13
    assert {x["upstream_id"] for x in payload["verification_tools"]} == {
        "UPSTREAM-015",
        "UPSTREAM-027",
        "UPSTREAM-032",
        "UPSTREAM-044",
        "UPSTREAM-051",
        "UPSTREAM-063",
        "UPSTREAM-064",
        "UPSTREAM-085",
        "UPSTREAM-092",
        "UPSTREAM-093",
        "UPSTREAM-101",
        "UPSTREAM-108",
        "UPSTREAM-111",
    }


def test_verification_cli_plan_contains_all_required_categories(project_root, capsys):
    assert main(["verification", "plan", "--root", str(project_root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["checks"]) == 14
    assert set(payload["required_categories"]) == {x["category"] for x in payload["checks"]}


def test_verification_cli_journeys_pass(project_root, capsys):
    assert main(["verification", "journeys", "--root", str(project_root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["journeys"]) == 4
    assert all(x["state"] == "PASS" for x in payload["results"])


def test_verification_cli_browser_requires_explicit_approval(project_root, capsys):
    code = main(["verification", "browser", "--root", str(project_root)])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "configuration_invalid"
    assert "--apply and --approve" in payload["message"]


def test_verification_cli_full_run_requires_explicit_approval(project_root, tmp_path, capsys):
    code = main(
        [
            "verification",
            "run",
            "--root",
            str(project_root),
            "--database",
            str(tmp_path / "v.sqlite"),
        ]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "--apply and --approve" in payload["message"]


def test_verification_cli_simulation_is_machine_readable(project_root, capsys):
    assert (
        main(["verification", "simulate", "--root", str(project_root), "--scenario", "golden"]) == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["verification_simulation"]["passed"] is True


def test_verification_impact_cli_derives_required_categories(project_root, capsys):
    code = main(
        [
            "verification",
            "impact",
            "--root",
            str(project_root),
            "--changed-path",
            "src/project_pipeline/budget/governor.py",
            "--requirement-id",
            "REQ-BUDGET-0001",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    categories = set(payload["test_impact"]["required_categories"])
    assert {"CONTRACT", "INTEGRATION", "FAULT"}.issubset(categories)
