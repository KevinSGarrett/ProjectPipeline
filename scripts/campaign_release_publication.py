"""Publish a campaign-attested release and emit a remote byte-verification receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.live_qualification import (  # noqa: E402
    _DEFAULT_REPOSITORY_SLUG,
    _github_repository_slug_from_url,
    _resolve_github_token,
)
from project_pipeline.autonomy_runtime.release_publication import (  # noqa: E402
    publish_campaign_release,
)
from project_pipeline.github_steward.adapter import GitHubRestAdapter  # noqa: E402
from project_pipeline.github_steward.mock import MockGitHubAdapter  # noqa: E402


def _repository_slug(root: Path) -> str:
    project = root / "config" / "project.json"
    if project.is_file():
        payload = json.loads(project.read_text(encoding="utf-8"))
        value = payload.get("repository")
        if isinstance(value, str):
            slug = _github_repository_slug_from_url(value)
            if slug:
                return slug
    return _DEFAULT_REPOSITORY_SLUG


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--campaign-database", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--evidence-path", type=Path, required=True)
    parser.add_argument("--desktop-dir", type=Path)
    parser.add_argument("--provider", choices=("github", "mock"), default="github")
    parser.add_argument("--fixture-desktop", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve()
    slug = _repository_slug(root)
    if args.fixture_desktop and args.provider != "mock":
        raise SystemExit("fixture_desktop_is_test_only")
    if args.provider == "mock":
        remote = MockGitHubAdapter(repository_slug=slug)
    else:
        token, _source = _resolve_github_token(root)
        if not token:
            raise SystemExit("github_token_unavailable")
        remote = GitHubRestAdapter(token=token)
    try:
        payload = publish_campaign_release(
            repository_root=root,
            campaign_database=args.campaign_database,
            campaign_id=args.campaign_id,
            evidence_path=args.evidence_path,
            repository_slug=slug,
            remote=remote,
            actor_id="actor:campaign-release-publisher",
            authorization_id=f"auth:campaign-release:{args.campaign_id}",
            correlation_id=f"corr:campaign-release:{args.campaign_id}",
            desktop_artifact_dir=args.desktop_dir,
            fixture_desktop=bool(args.fixture_desktop),
        )
    except Exception as exc:  # no secrets are included in the structured failure receipt
        print(json.dumps({"publication": {"state": "FAILED"}, "reason": str(exc)}))
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
