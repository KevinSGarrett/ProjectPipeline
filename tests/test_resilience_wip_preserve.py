from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from project_pipeline.resilience.wip_preserve import WipPreserveError, preserve_uncommitted_work


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
    _git(root, "init")
    _git(root, "config", "user.email", "wip@example.test")
    _git(root, "config", "user.name", "WIP Preserve")
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "init")
    return root


def test_preserve_uncommitted_work_copies_dirty_files_and_skips_secrets(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    (root / "notes.md").write_text("untracked\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    destination = tmp_path / "bundle"
    dry = preserve_uncommitted_work(root, destination, apply=False)
    assert dry["applied"] is False
    assert "tracked.txt" in dry["recoverable_paths"]
    assert "notes.md" in dry["recoverable_paths"]
    assert ".env" in dry["skipped_secret_paths"]
    assert not destination.exists()
    applied = preserve_uncommitted_work(root, destination, apply=True)
    assert applied["preserved"] is True
    assert (destination / "files" / "tracked.txt").read_text(encoding="utf-8") == "dirty\n"
    assert (destination / "files" / "notes.md").read_text(encoding="utf-8") == "untracked\n"
    assert not (destination / "files" / ".env").exists()
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "dirty\n"
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_files_deleted"] is False
    assert manifest["head_sha"] == applied["head_sha"]
    assert len(applied["head_sha"]) == 40


def test_preserve_uncommitted_work_rejects_unsafe_destination(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    (root / "extra.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(WipPreserveError):
        preserve_uncommitted_work(root, Path("C:/"), apply=False)
    with pytest.raises(WipPreserveError):
        preserve_uncommitted_work(root, root, apply=False)
    with pytest.raises(WipPreserveError):
        preserve_uncommitted_work(root, root / ".git" / "wip", apply=True)


def test_preserve_uncommitted_work_is_noop_when_clean(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    destination = tmp_path / "empty-bundle"
    payload = preserve_uncommitted_work(root, destination, apply=True)
    assert payload["preserved"] is False
    assert payload["file_count"] == 0
    assert not destination.exists()
