from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from project_pipeline.domain.github import WorktreeState
from project_pipeline.github_steward.local_git import (
    LocalGitError,
    LocalGitRepository,
    evaluate_branch_guardian,
)


def run(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, text=True, capture_output=True
    )


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "init", "-b", "main")
    run(repo, "config", "user.email", "test@example.com")
    run(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("# Repo\n")
    run(repo, "add", "README.md")
    run(repo, "commit", "-m", "initial")
    run(repo, "remote", "add", "origin", "https://github.com/owner/repo.git")
    return repo


def test_snapshot_and_branch_guardian_block_default_branch(tmp_path):
    repo = make_repo(tmp_path)
    adapter = LocalGitRepository(repo)
    snapshot = adapter.snapshot()
    assert snapshot.repository_slug == "owner/repo"
    assert snapshot.current_branch == "main"
    decision = evaluate_branch_guardian(snapshot, adapter.branches(), adapter.worktrees())
    assert not decision.safe_for_work
    assert any(item.code == "DEFAULT_BRANCH_ACTIVE" for item in decision.findings)


def test_feature_branch_is_safe_when_clean(tmp_path):
    repo = make_repo(tmp_path)
    run(repo, "switch", "-c", "feature/PP-TASK-1")
    adapter = LocalGitRepository(repo)
    decision = evaluate_branch_guardian(adapter.snapshot(), adapter.branches(), adapter.worktrees())
    assert decision.safe_for_work
    assert decision.safe_for_cleanup


def test_dirty_worktree_is_preserved(tmp_path):
    repo = make_repo(tmp_path)
    run(repo, "switch", "-c", "feature/PP-TASK-1")
    (repo / "README.md").write_text("changed\n")
    adapter = LocalGitRepository(repo)
    snapshot = adapter.snapshot()
    assert snapshot.dirty
    decision = evaluate_branch_guardian(snapshot, adapter.branches(), adapter.worktrees())
    assert decision.safe_for_work
    assert not decision.safe_for_cleanup


def test_branch_creation_is_dry_run_by_default(tmp_path):
    repo = make_repo(tmp_path)
    adapter = LocalGitRepository(repo)
    result = adapter.create_branch("feature/test", "HEAD")
    assert result["mode"] == "DRY_RUN"
    assert "feature/test" not in {item.name for item in adapter.branches()}
    adapter.create_branch("feature/test", "HEAD", apply=True)
    assert "feature/test" in {item.name for item in adapter.branches()}


def test_worktree_creation_and_dirty_removal_protection(tmp_path):
    repo = make_repo(tmp_path)
    adapter = LocalGitRepository(repo)
    adapter.create_branch("feature/worktree", "HEAD", apply=True)
    wt = tmp_path / "worktree"
    adapter.create_worktree(wt, "feature/worktree", apply=True)
    assert any(
        Path(item.path) == wt and item.state is WorktreeState.CLEAN for item in adapter.worktrees()
    )
    (wt / "README.md").write_text("dirty\n")
    with pytest.raises(LocalGitError, match="dirty worktree"):
        adapter.remove_worktree(wt, apply=True)


def test_invalid_branch_name_is_rejected(tmp_path):
    adapter = LocalGitRepository(make_repo(tmp_path))
    with pytest.raises(LocalGitError):
        adapter.create_branch("-bad", "HEAD", apply=True)
