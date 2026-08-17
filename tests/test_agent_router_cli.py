import json

from project_pipeline.cli import main


def test_agent_router_registry_and_route_are_executable(capsys, tmp_path):
    root = __import__("pathlib").Path(__file__).parents[1]
    db = tmp_path / "router.db"
    assert main(["agent-router", "registry", "--root", str(root), "--database", str(db)]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "agent-router",
                "route",
                "--root",
                str(root),
                "--database",
                str(db),
                "--capability",
                "routine_reasoning",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert (
        data["routing_decision"]["selected_provider_id"] == "provider:mock-local"
        and data["dry_run"] is True
    )


def test_agent_router_unqualified_external_capability_fails_closed(capsys, tmp_path):
    root = __import__("pathlib").Path(__file__).parents[1]
    code = main(
        [
            "agent-router",
            "route",
            "--root",
            str(root),
            "--database",
            str(tmp_path / "router.db"),
            "--capability",
            "code_implementation",
            "--quality-tier",
            "strong",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 1 and data["routing_decision"]["selected_provider_id"] is None


def test_agent_router_simulation_demonstrates_fallback(capsys, tmp_path):
    root = __import__("pathlib").Path(__file__).parents[1]
    assert (
        main(
            [
                "agent-router",
                "simulate",
                "--root",
                str(root),
                "--database",
                str(tmp_path / "router.db"),
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["simulation"]["succeeded"] and data["simulation"]["providers"] == [
        "provider:primary",
        "provider:fallback",
    ]


def test_agent_router_simulate_apply_requires_approve(capsys, tmp_path):
    root = __import__("pathlib").Path(__file__).parents[1]
    code = main(
        [
            "agent-router",
            "simulate",
            "--root",
            str(root),
            "--database",
            str(tmp_path / "router.db"),
            "--scenario",
            "circuit",
            "--apply",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 2 and data["applied"] is False
    assert (
        main(
            [
                "agent-router",
                "simulate",
                "--root",
                str(root),
                "--database",
                str(tmp_path / "router.db"),
                "--scenario",
                "circuit",
                "--apply",
                "--approve",
            ]
        )
        == 0
    )
    approved = json.loads(capsys.readouterr().out)
    assert approved["applied"] is True
    assert approved["simulation"]["closed"] is True
