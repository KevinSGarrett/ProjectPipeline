from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
