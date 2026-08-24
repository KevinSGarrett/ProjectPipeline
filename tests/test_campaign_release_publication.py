from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime import release_publication
from project_pipeline.github_steward import draft_release
from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.github_steward.mock import MockGitHubAdapter
from project_pipeline.release_factory.bundle import BoundArtifact, ReleaseBundle
from project_pipeline.release_factory.version import ReleaseVersionAuthority

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
TREE = "b" * 40


def _bundle(tmp_path: Path, *, desktop_bound: bool = True) -> ReleaseBundle:
    output = tmp_path / "bundle"
    output.mkdir()
    payload = b"candidate-bytes"
    artifact = output / "project_pipeline-0.9.0-py3-none-any.whl"
    artifact.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    version = ReleaseVersionAuthority(
        bundle_version="0.9.0",
        desktop_version="0.9.0",
        source_sha=SHA,
        source_tree=TREE,
        sources={"test": "0.9.0"},
        dual_identity=False,
        tag_name=f"v0.9.0-rc.{SHA[:12]}",
    )
    return ReleaseBundle(
        cache_key="c" * 64,
        version=version,
        artifacts=(
            BoundArtifact(
                kind="wheel",
                name=artifact.name,
                sha256=digest,
                size_bytes=len(payload),
                source_sha=SHA,
                source_tree=TREE,
            ),
        ),
        output_dir=str(output),
        desktop_bound=desktop_bound,
    )


def _eligible(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {
        "campaign_id": "QCAMP-TEST",
        "integrated_sha": SHA,
        "integrated_tree": TREE,
        "qualification_run_id": "QRUN-TEST",
        "attested_elapsed_seconds": 72 * 3600,
    }


def _patch_campaign_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_publication, "verify_campaign_publication_eligibility", _eligible)
    monkeypatch.setattr(draft_release, "_verify_campaign_publication", _eligible)


def test_campaign_release_publication_finalizes_only_after_remote_bytes_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path)
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"  # test seam for a local byte-level fake

    result = release_publication.publish_campaign_release(
        repository_root=ROOT,
        campaign_database=tmp_path / "campaign.sqlite3",
        campaign_id="QCAMP-TEST",
        evidence_path=tmp_path / "evidence",
        repository_slug="owner/repo",
        remote=remote,
        actor_id="actor:test",
        authorization_id="auth:test",
        correlation_id="corr:test",
    )

    publication = result["publication"]
    assert publication["state"] == "PUBLISHED"
    assert publication["draft"] is False
    assert publication["provider"] == "github-rest"
    assert publication["fixture_desktop"] is False
    assert publication["target_commitish"] == SHA
    assert publication["assets"][0]["bytes_verified"] is True
    assert publication["assets"][0]["sha256"] == publication["assets"][0]["remote_sha256"]
    assert (tmp_path / "evidence" / "remote-acquired" / "acquired_manifest.json").is_file()


def test_campaign_release_publication_rejects_unbound_desktop_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication,
        "build_release_bundle",
        lambda *_args, **_kwargs: _bundle(tmp_path, desktop_bound=False),
    )

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    with pytest.raises(GitHubStewardError, match="real bound desktop artifacts"):
        release_publication.publish_campaign_release(
            repository_root=ROOT,
            campaign_database=tmp_path / "campaign.sqlite3",
            campaign_id="QCAMP-TEST",
            evidence_path=tmp_path / "evidence",
            repository_slug="owner/repo",
            remote=remote,
            actor_id="actor:test",
            authorization_id="auth:test",
            correlation_id="corr:test",
        )


def test_campaign_release_publication_rejects_fixture_desktop_for_live_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path, desktop_bound=True)
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"  # emulate a non-test remote without invoking it

    with pytest.raises(GitHubStewardError, match="test-only"):
        release_publication.publish_campaign_release(
            repository_root=ROOT,
            campaign_database=tmp_path / "campaign.sqlite3",
            campaign_id="QCAMP-TEST",
            evidence_path=tmp_path / "evidence",
            repository_slug="owner/repo",
            remote=remote,
            actor_id="actor:test",
            authorization_id="auth:test",
            correlation_id="corr:test",
            fixture_desktop=True,
        )


def test_campaign_release_publication_rejects_mock_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: _bundle(tmp_path)
    )
    with pytest.raises(GitHubStewardError, match="GitHub REST adapter"):
        release_publication.publish_campaign_release(
            repository_root=ROOT,
            campaign_database=tmp_path / "campaign.sqlite3",
            campaign_id="QCAMP-TEST",
            evidence_path=tmp_path / "evidence",
            repository_slug="owner/repo",
            remote=MockGitHubAdapter(repository_slug="owner/repo"),
            actor_id="actor:test",
            authorization_id="auth:test",
            correlation_id="corr:test",
        )
