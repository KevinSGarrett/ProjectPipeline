from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_pipeline.cli import main


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "README.md").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/owner/repo.git"],
        check=True,
    )
    return repo


def test_repository_inspect_and_guardian_are_machine_readable(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code = main(
        [
            "repository",
            "inspect",
            "--root",
            str(Path.cwd()),
            "--repository-root",
            str(repo),
            "--database",
            str(tmp_path / "state.db"),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["snapshot"]["repository_slug"] == "owner/repo"
    assert payload["guardian"]["safe_for_work"] is False


def test_create_branch_defaults_to_dry_run(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code = main(
        [
            "repository",
            "create-branch",
            "--root",
            str(Path.cwd()),
            "--repository-root",
            str(repo),
            "--database",
            str(tmp_path / "state.db"),
            "--branch",
            "feature/test",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "DRY_RUN"
    names = subprocess.run(
        ["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert "feature/test" not in names


def test_local_mutation_requires_approval(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code = main(
        [
            "repository",
            "create-branch",
            "--root",
            str(Path.cwd()),
            "--repository-root",
            str(repo),
            "--database",
            str(tmp_path / "state.db"),
            "--branch",
            "feature/test",
            "--apply",
        ]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "requires both --apply and --approve" in payload["message"]


def test_github_status_with_mock_provider_has_no_remote_write(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code = main(
        [
            "github",
            "status",
            "--root",
            str(Path.cwd()),
            "--repository-root",
            str(repo),
            "--database",
            str(tmp_path / "state.db"),
            "--repository-slug",
            "owner/repo",
            "--provider",
            "mock",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["repository_slug"] == "owner/repo"
    assert payload["operation_counts"] == {}
