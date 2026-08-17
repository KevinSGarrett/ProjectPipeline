from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.github_steward.service import RepositorySteward
from project_pipeline.github_steward.worktrunk import WorktrunkAdapter


def test_worktrunk_create_is_dry_run_until_approved(tmp_path: Path) -> None:
    calls = []

    def runner(argv, cwd, timeout):
        calls.append((tuple(argv), cwd, timeout))
        return subprocess.CompletedProcess(argv, 0, "", "")

    adapter = WorktrunkAdapter(runner=runner)
    plan = adapter.create_plan(tmp_path, "feature-safe", base="main")
    result = adapter.execute(plan)
    assert result["state"] == "DRY_RUN"
    assert not calls
    assert plan.argv[:4] == ("wt", "switch", "--create", "feature-safe")
    assert "--no-cd" in plan.argv and "--no-hooks" in plan.argv


def test_worktrunk_json_list_and_approved_mutation_use_fixed_argv(tmp_path: Path) -> None:
    calls = []

    def runner(argv, cwd, timeout):
        calls.append(tuple(argv))
        body = json.dumps([{"branch": "main", "path": str(tmp_path)}]) if "list" in argv else ""
        return subprocess.CompletedProcess(argv, 0, body, "")

    adapter = WorktrunkAdapter(runner=runner)
    observed = adapter.execute(adapter.list_plan(tmp_path))
    assert observed["state"] == "OBSERVED" and observed["output"][0]["branch"] == "main"
    applied = adapter.execute(adapter.create_plan(tmp_path, "feature-safe"), approved=True)
    assert applied["state"] == "APPLIED"
    assert calls[0] == ("wt", "list", "--format=json")


def test_repository_steward_worktrunk_is_dry_run_and_refuses_protected_main(tmp_path: Path) -> None:
    class Local:
        def __init__(self) -> None:
            self.root = tmp_path

        def snapshot(self):
            return type(
                "Snap",
                (),
                {"current_branch": "main", "default_branch": "main"},
            )()

    steward = RepositorySteward(local=Local(), remote=object(), store=object())
    adapter = WorktrunkAdapter(
        runner=lambda argv, cwd, timeout: subprocess.CompletedProcess(argv, 0, "", "")
    )
    dry = steward.plan_worktrunk(adapter, "feature-safe")
    assert dry["state"] == "DRY_RUN"
    with pytest.raises(GitHubStewardError, match="protected main"):
        steward.plan_worktrunk(adapter, "feature-safe", approved=True)
