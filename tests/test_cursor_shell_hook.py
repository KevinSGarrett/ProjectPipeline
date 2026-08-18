from __future__ import annotations

import json
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".cursor" / "hooks" / "guard_shell.py"
PYTHON = Path("C:/Project_X/.venv/Scripts/python.exe")


def _run_hook(command: str, tmp_path: Path) -> dict:
    import subprocess

    proc = subprocess.run(
        [str(PYTHON), str(HOOK)],
        input=json.dumps({"command": command}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_hook_allows_governed_git_and_gh(tmp_path):
    assert _run_hook("git status", tmp_path)["permission"] == "allow"
    assert _run_hook("git push -u origin HEAD", tmp_path)["permission"] == "allow"
    assert _run_hook("gh pr list --state open", tmp_path)["permission"] == "allow"


def test_hook_blocks_force_push_and_hard_reset(tmp_path):
    assert _run_hook("git push --force origin main", tmp_path)["permission"] == "deny"
    assert _run_hook("git reset --hard HEAD", tmp_path)["permission"] == "deny"
    assert _run_hook("git clean -fdx", tmp_path)["permission"] == "deny"


def test_hook_emits_json_decision_on_empty_stdin():
    import subprocess

    proc = subprocess.run(
        [str(PYTHON), str(HOOK)],
        input="",
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["permission"] == "allow"
