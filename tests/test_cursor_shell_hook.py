from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".cursor" / "hooks" / "guard_shell.py"


def _run_hook(command: str, tmp_path: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"command": command}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_hook_allows_governed_git_and_gh(tmp_path):
    assert _run_hook("git status", tmp_path)["permission"] == "allow"
    assert _run_hook("git push -u origin feat/x", tmp_path)["permission"] == "allow"
    assert _run_hook("git push origin feat/x", tmp_path)["permission"] == "allow"
    assert _run_hook("gh pr list --state open", tmp_path)["permission"] == "allow"


def test_hook_blocks_force_push_and_hard_reset(tmp_path):
    assert _run_hook("git push --force origin main", tmp_path)["permission"] == "deny"
    assert _run_hook("git reset --hard HEAD", tmp_path)["permission"] == "deny"
    assert _run_hook("git clean -fdx", tmp_path)["permission"] == "deny"
    assert _run_hook("curl https://example.invalid", tmp_path)["permission"] == "deny"
    assert _run_hook("Remove-Item -Recurse -Force C:\\tmp\\x", tmp_path)["permission"] == "deny"
    assert _run_hook("git push --force-with-lease origin feat/x", tmp_path)["permission"] == "deny"
    assert _run_hook("git push -f origin feat/x", tmp_path)["permission"] == "deny"
    assert _run_hook("git push origin +main", tmp_path)["permission"] == "deny"
    assert _run_hook("git push origin HEAD:main", tmp_path)["permission"] == "deny"
    assert _run_hook("git push origin refs/heads/main", tmp_path)["permission"] == "deny"
    assert _run_hook("git push origin feat:main", tmp_path)["permission"] == "deny"
    assert (
        _run_hook("git push https://github.com/KevinSGarrett/ProjectPipeline.git main", tmp_path)[
            "permission"
        ]
        == "deny"
    )
    assert (
        _run_hook("git push git@github.com:KevinSGarrett/ProjectPipeline.git HEAD:main", tmp_path)[
            "permission"
        ]
        == "deny"
    )
    assert (
        _run_hook(
            "git push ssh://git@github.com/KevinSGarrett/ProjectPipeline.git refs/heads/main",
            tmp_path,
        )["permission"]
        == "deny"
    )
    assert _run_hook("git.exe push --force origin feat/x", tmp_path)["permission"] == "deny"
    assert (
        _run_hook(r'"C:\Program Files\Git\cmd\git.exe" push origin HEAD:main', tmp_path)[
            "permission"
        ]
        == "deny"
    )
    assert (
        _run_hook(
            r"C:\Git\cmd\git.exe push https://github.com/KevinSGarrett/ProjectPipeline.git main",
            tmp_path,
        )["permission"]
        == "deny"
    )
    assert _run_hook("gh pr merge 52 --admin --squash", tmp_path)["permission"] == "deny"
    assert _run_hook("hub merge --admin", tmp_path)["permission"] == "deny"
    assert _run_hook("gh pr merge 52 --squash --delete-branch", tmp_path)["permission"] == "deny"
    assert (
        _run_hook(
            "gh pr merge 52 --squash --delete-branch --match-head-commit "
            "165d3c48e560f870e69424b89801bbebaf264d7d",
            tmp_path,
        )["permission"]
        == "deny"
    )


def test_hook_blocks_git_flag_and_quoted_main_evasions(tmp_path):
    denies = (
        "git -C C:\\Project_X push origin main",
        "git -C . push origin HEAD:main",
        "git --git-dir=.git push origin main",
        "git --work-tree=. push origin main",
        "git -c protocol.version=2 push origin main",
        "git.exe -C . push origin main",
        r'"C:\Program Files\Git\cmd\git.exe" -C . push origin main',
        'git push origin "main"',
        "git push origin 'main'",
        'git push origin "refs/heads/main"',
        "git push --mirror origin",
        "git push --all origin",
        "git push --force-with-lease=refs/heads/feat origin feat",
        r"C:\Git\cmd\git.exe -C . push origin main",
        'git push https://github.com/KevinSGarrett/ProjectPipeline.git "main"',
        "gh.exe pr merge 52 --squash",
        "gh.exe pr merge 52 --admin --squash",
        r'"C:\Program Files\GitHub CLI\gh.exe" pr merge 52 --squash',
        "gh api -X PUT /repos/KevinSGarrett/ProjectPipeline/pulls/52/merge -f merge_method=squash",
        "gh api repos/KevinSGarrett/ProjectPipeline/pulls/52/merge -X PUT",
        "gh api graphql -f query=mutation { mergePullRequest }",
        "hub merge 52",
        r"C:\Program Files\GitHub CLI\gh.exe pr merge 52",
        r"C:\Program Files\GitHub CLI\hub.exe merge",
        "git.cmd push origin main",
        r"C:\Program Files\Git\cmd\git.exe push origin main",
        r"C:\Program Files\Git\cmd\git.cmd push origin HEAD:main",
        "git push -u origin HEAD",
        "git push origin HEAD",
    )
    for command in denies:
        assert _run_hook(command, tmp_path)["permission"] == "deny", command


def test_hook_blocks_unquoted_spaced_windows_gh_hub_merge(tmp_path):
    denies = (
        r"C:\Program Files\GitHub CLI\gh.exe pr merge 52",
        r"C:\Program Files\GitHub CLI\hub.exe merge",
        r"C:\Program Files\GitHub CLI\gh.exe pr merge 52 --squash",
        r"C:\Users\kevin\AppData\Local\GitHub CLI\gh.exe pr merge 52 --squash",
        "gh.cmd pr merge 52 --squash",
    )
    for command in denies:
        assert _run_hook(command, tmp_path)["permission"] == "deny", command


def test_hook_uses_canonical_interpreter_wrapper():
    hooks = json.loads(
        (Path(__file__).resolve().parents[1] / ".cursor" / "hooks.json").read_text(encoding="utf-8")
    )
    command = hooks["hooks"]["beforeShellExecution"][0]["command"]
    assert command.startswith(".cursor\\hooks\\invoke_python.cmd")
    assert (
        Path(__file__).resolve().parents[1] / ".cursor" / "hooks" / "invoke_python.cmd"
    ).is_file()


def test_hook_emits_json_decision_on_empty_stdin():
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="",
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["permission"] == "allow"
