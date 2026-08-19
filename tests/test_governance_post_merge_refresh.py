from __future__ import annotations

import subprocess
from pathlib import Path

from project_pipeline.governance.post_merge_refresh import plan_post_merge_refresh


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "gov@example.test")
    _git(root, "config", "user.name", "Gov Refresh")
    (root / "README.md").write_text("ok\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "init")
    return root


def test_post_merge_refresh_preserves_dirty_pinned_and_root(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    _git(root, "switch", "-c", "feature/clean")
    _git(root, "switch", "main")
    _git(root, "switch", "-c", "feature/dirty")
    _git(root, "switch", "main")
    clean = tmp_path / "feature-clean"
    dirty = tmp_path / "feature-dirty"
    pinned = tmp_path / "cycle-012-pp385-qualify"
    _git(root, "worktree", "add", str(clean), "feature/clean")
    _git(root, "worktree", "add", str(dirty), "feature/dirty")
    _git(root, "worktree", "add", str(pinned), "HEAD")
    (dirty / "notes.txt").write_text("dirty\n", encoding="utf-8")
    payload = plan_post_merge_refresh(root, apply=False)
    by_path = {item["path"]: item for item in payload["workspaces"]}
    assert by_path[str(root.resolve())]["disposition"] == "PRESERVE"
    assert by_path[str(clean.resolve())]["disposition"] == "CLOSE_ELIGIBLE"
    assert by_path[str(dirty.resolve())]["disposition"] == "PRESERVE"
    assert by_path[str(pinned.resolve())]["disposition"] == "PRESERVE"
    assert payload["user_action_required"] is False
    assert payload["applied"] is False
    assert clean.exists()


def test_post_merge_refresh_closes_only_clean_eligible_worktree(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    _git(root, "switch", "-c", "feature/close-me")
    _git(root, "switch", "main")
    clean = tmp_path / "close-me"
    _git(root, "worktree", "add", str(clean), "feature/close-me")
    payload = plan_post_merge_refresh(root, apply=True)
    assert any(item["closed"] for item in payload["workspaces"] if "close-me" in item["path"])
    assert not clean.exists()
    assert payload["ok"] is True


def test_post_merge_refresh_rejects_identity_mismatch(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    payload = plan_post_merge_refresh(
        root,
        expected_sha="0" * 40,
        expected_tree="1" * 40,
        apply=False,
    )
    assert payload["ok"] is False
    assert payload["identity_errors"]
