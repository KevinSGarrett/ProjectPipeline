from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_pipeline.autonomy_runtime.nonduration import (
    REMAINING_ACCEPTANCE,
    evaluate_nonduration_qualification,
)
from project_pipeline.github_steward.local_git import LocalGitRepository

ROOT = Path(__file__).resolve().parents[1]


def test_nonduration_stages_are_present_and_duration_remains() -> None:
    report = evaluate_nonduration_qualification(ROOT)
    assert report["ok"] is True
    assert report["implementation_state"] == "PARTIALLY_IMPLEMENTED"
    assert report["remaining_acceptance"] == list(REMAINING_ACCEPTANCE)
    assert all(item["present"] for item in report["stages"])
    assert "real 24h qualification" in report["remaining_acceptance"]
    assert "Completion Gate" in report["remaining_acceptance"]


def test_isolated_git_worktree_journey_survives_add_and_remove(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "nondur@example.test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Nonduration"],
        check=True,
        capture_output=True,
    )
    (repo / "tracked.txt").write_text("journey\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init isolated journey"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "branch", "feat/isolated-journey"],
        check=True,
        capture_output=True,
    )
    local = LocalGitRepository(repo)
    worktree = tmp_path / "lane"
    created = local.create_worktree(worktree, "feat/isolated-journey", apply=True)
    assert created["applied"] is True
    assert (worktree / "tracked.txt").read_text(encoding="utf-8") == "journey\n"
    (worktree / "progress.json").write_text(
        json.dumps({"selected": True, "lane": "unrelated-ready"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(worktree), "add", "progress.json"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(worktree), "commit", "-m", "isolated lane progress"],
        check=True,
        capture_output=True,
    )
    removed = local.remove_worktree(worktree, apply=True)
    assert removed["applied"] is True
    assert not worktree.exists()


def test_pdef_0011_cannot_claim_implemented_before_duration_stages(tmp_path: Path) -> None:
    report = evaluate_nonduration_qualification(ROOT)
    assert report["implementation_state"] != "IMPLEMENTED"
    core = next(
        json.loads(line)
        for line in (ROOT / "plans/_traceability/requirements.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if '"REQ-PDEF-0011"' in line and json.loads(line)["requirement_id"] == "REQ-PDEF-0011"
    )
    assert core["implementation_state"] in {"PLANNED_ONLY", "PARTIALLY_IMPLEMENTED"}
    assert core["evidence_ids"], "PDEF-0011 must keep evidence identifiers"
    assert set(report["remaining_acceptance"]) == set(REMAINING_ACCEPTANCE)
