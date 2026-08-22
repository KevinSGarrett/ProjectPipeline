from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.live_qualification import (  # noqa: E402
    _DEFAULT_REPOSITORY_SLUG,
    _github_repository_slug_from_url,
    _resolve_github_token,
)
from project_pipeline.github_steward.adapter import GitHubRestAdapter  # noqa: E402
from project_pipeline.github_steward.ports import GitHubWriteContext  # noqa: E402


def _repository_slug(root: Path) -> str:
    project_json = root / "config" / "project.json"
    if project_json.is_file():
        repository_url = json.loads(project_json.read_text(encoding="utf-8")).get("repository", "")
        if isinstance(repository_url, str):
            slug = _github_repository_slug_from_url(repository_url)
            if slug is not None:
                return slug
    return _DEFAULT_REPOSITORY_SLUG


def _current_branch(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("unable to resolve current branch")
    return completed.stdout.strip()


def _head_sha(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("unable to resolve HEAD")
    return completed.stdout.strip()


def _push_branch(root: Path, branch: str) -> dict[str, object]:
    completed = subprocess.run(
        ["git", "-C", str(root), "push", "-u", "origin", branch],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _find_open_pull(repository_slug: str, branch: str) -> dict[str, object] | None:
    completed = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repository_slug,
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,url,state,headRefOid",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    rows = json.loads(completed.stdout)
    if not rows:
        return None
    item = rows[0]
    return {
        "number": item.get("number"),
        "url": item.get("url"),
        "head_sha": item.get("headRefOid"),
        "state": item.get("state"),
    }


def _pull_url(repository_slug: str, number: int) -> str:
    return f"https://github.com/{repository_slug}/pull/{number}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Push a feature branch and create a governed GitHub pull request"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--skip-push", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    branch = _current_branch(root)
    head_sha = _head_sha(root)
    repository_slug = _repository_slug(root)
    token, token_source = _resolve_github_token(root)
    if not token:
        print(json.dumps({"ok": False, "reason": "github_token_unavailable"}, indent=2))
        return 1

    push_result = None
    if not args.skip_push:
        push_result = _push_branch(root, branch)
        if push_result["exit_code"] != 0:
            print(
                json.dumps(
                    {"ok": False, "reason": "git_push_failed", "push": push_result},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1

    adapter = GitHubRestAdapter(token=token)
    existing = _find_open_pull(repository_slug, branch)
    if existing is not None:
        readback = adapter.get_pull_request(repository_slug, int(existing["number"]))
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "existing_pull",
                    "repository_slug": repository_slug,
                    "branch": branch,
                    "head_sha": head_sha,
                    "token_source": token_source,
                    "push": push_result,
                    "pull": existing,
                    "readback_head_sha": None if readback is None else readback.head_sha,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    context = GitHubWriteContext(
        actor_id="actor:pp384-steward",
        correlation_id="corr:pp384-steward-create-pull",
        idempotency_key=f"pp384-create-pull:{branch}:{head_sha[:12]}",
        authorization_id="auth:pp384-steward-create-pull",
        expected_head_sha=head_sha,
    )
    created = adapter.create_pull_request(
        repository_slug,
        head=branch,
        base=args.base,
        title=args.title,
        body=args.body,
        draft=args.draft,
        context=context,
    )
    readback = adapter.get_pull_request(repository_slug, created.number)
    ok = readback is not None and readback.head_sha.lower() == head_sha.lower()
    print(
        json.dumps(
            {
                "ok": ok,
                "mode": "created_pull",
                "repository_slug": repository_slug,
                "branch": branch,
                "head_sha": head_sha,
                "token_source": token_source,
                "push": push_result,
                "pull": {
                    "number": created.number,
                    "url": _pull_url(repository_slug, created.number),
                    "head_sha": created.head_sha,
                    "state": created.state.value,
                },
                "readback_head_sha": None if readback is None else readback.head_sha,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
