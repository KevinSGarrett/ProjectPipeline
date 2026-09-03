from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime import release_publication
from project_pipeline.autonomy_runtime.admitted_release import write_admitted_release_inventory
from project_pipeline.contracts import AdapterErrorCategory
from project_pipeline.github_steward import draft_release
from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.github_steward.persistence import GitHubStewardStore
from project_pipeline.release_factory.bundle import BoundArtifact, ReleaseBundle
from project_pipeline.release_factory.version import ReleaseVersionAuthority
from project_pipeline.release_hardening import pre_admission

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
TREE = "b" * 40
ADMITTED_DRAFT_ID = 380237674
ADMITTED_ASSET_ID = 539058355


def _bundle(tmp_path: Path, *, desktop_bound: bool = True, payload: bytes = b"candidate-bytes") -> ReleaseBundle:
    output = tmp_path / "bundle"
    output.mkdir(exist_ok=True)
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


def _inventory_for(bundle: ReleaseBundle, *, draft_id: int = ADMITTED_DRAFT_ID) -> dict[str, object]:
    artifact = bundle.artifacts[0]
    return {
        "draft_id": draft_id,
        "tag_name": bundle.version.tag_name,
        "target_commitish": SHA,
        "source_sha": SHA,
        "source_tree": TREE,
        "assets": [
            {
                "id": ADMITTED_ASSET_ID,
                "name": artifact.name,
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
            }
        ],
    }


def _seed_admitted(
    remote: object,
    bundle: ReleaseBundle,
    evidence: Path,
    *,
    draft_id: int = ADMITTED_DRAFT_ID,
    payload: bytes = b"candidate-bytes",
) -> None:
    name = bundle.artifacts[0].name
    remote.seed_admitted_draft(
        repository_slug="owner/repo",
        release_id=draft_id,
        tag_name=bundle.version.tag_name,
        target_commitish=SHA,
        assets={name: payload},
        asset_ids={name: ADMITTED_ASSET_ID},
    )
    write_admitted_release_inventory(evidence, _inventory_for(bundle, draft_id=draft_id))


def _patch_campaign_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_publication, "verify_campaign_publication_eligibility", _eligible)
    monkeypatch.setattr(draft_release, "_verify_campaign_publication", _eligible)


def _publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    bundle: ReleaseBundle | None = None,
    remote: object | None = None,
    fixture_desktop: bool = False,
):
    bundle = bundle or _bundle(tmp_path)
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
    if remote is None:
        remote = __import__(
            "project_pipeline.github_steward.mock", fromlist=["MockGitHubAdapter"]
        ).MockGitHubAdapter(repository_slug="owner/repo")
        remote.provider_id = "github-rest"
        _seed_admitted(remote, bundle, tmp_path / "evidence")
    return release_publication.publish_campaign_release(
        repository_root=ROOT,
        campaign_database=tmp_path / "campaign.sqlite3",
        campaign_id="QCAMP-TEST",
        evidence_path=tmp_path / "evidence",
        repository_slug="owner/repo",
        remote=remote,
        actor_id="actor:test",
        authorization_id="auth:test",
        correlation_id="corr:test",
        fixture_desktop=fixture_desktop,
    ), remote, bundle


def test_campaign_release_publication_finalizes_only_after_remote_bytes_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    result, remote, _bundle_obj = _publish(tmp_path, monkeypatch)
    publication = result["publication"]
    assert publication["state"] == "PUBLISHED"
    assert publication["draft"] is False
    assert publication["provider"] == "github-rest"
    assert publication["fixture_desktop"] is False
    assert publication["target_commitish"] == SHA
    assert publication["release_id"] == ADMITTED_DRAFT_ID
    assert publication["assets"][0]["bytes_verified"] is True
    assert publication["assets"][0]["sha256"] == publication["assets"][0]["remote_sha256"]
    assert Path(publication["acquired_path"]).joinpath("acquired_manifest.json").is_file()
    assert not any(call[0] == "create_draft_release" for call in remote.calls)


def test_campaign_release_publication_rejects_unbound_desktop_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path, desktop_bound=False)
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    _seed_admitted(remote, bundle, tmp_path / "evidence")
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication,
        "build_release_bundle",
        lambda *_args, **_kwargs: bundle,
    )
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
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    _seed_admitted(remote, bundle, tmp_path / "evidence")
    with pytest.raises(GitHubStewardError, match="test-only"):
        _publish(tmp_path, monkeypatch, bundle=bundle, remote=remote, fixture_desktop=True)


def test_campaign_release_publication_rejects_mock_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    bundle = _bundle(tmp_path)
    write_admitted_release_inventory(tmp_path / "evidence", _inventory_for(bundle))
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
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


def test_publication_rejects_changed_bytes_at_same_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    admitted = _bundle(tmp_path, payload=b"admitted-bytes")
    rebuilt = _bundle(tmp_path, payload=b"replacement-bytes")
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    _seed_admitted(remote, admitted, tmp_path / "evidence", payload=b"admitted-bytes")
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: rebuilt
    )
    with pytest.raises(GitHubStewardError, match="changed bytes"):
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


def test_publication_rejects_missing_or_substituted_draft_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path)
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    write_admitted_release_inventory(tmp_path / "evidence", _inventory_for(bundle))
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
    with pytest.raises(GitHubStewardError, match="admitted draft identity is missing"):
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

    remote.seed_admitted_draft(
        repository_slug="owner/repo",
        release_id=999,
        tag_name=bundle.version.tag_name,
        target_commitish=SHA,
        assets={bundle.artifacts[0].name: b"candidate-bytes"},
        asset_ids={bundle.artifacts[0].name: ADMITTED_ASSET_ID},
    )
    with pytest.raises(GitHubStewardError, match="admitted draft identity"):
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


def test_publication_rejects_changed_tag_or_extra_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path)
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    remote.seed_admitted_draft(
        repository_slug="owner/repo",
        release_id=ADMITTED_DRAFT_ID,
        tag_name="v0.9.0-rc.other",
        target_commitish=SHA,
        assets={bundle.artifacts[0].name: b"candidate-bytes"},
        asset_ids={bundle.artifacts[0].name: ADMITTED_ASSET_ID},
    )
    write_admitted_release_inventory(tmp_path / "evidence", _inventory_for(bundle))
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
    with pytest.raises(GitHubStewardError, match="tag"):
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


def test_publication_rejects_missing_inventory_instead_of_creating_a_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path)
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
    with pytest.raises(GitHubStewardError, match="admitted release inventory"):
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
    assert not any(call[0] == "create_draft_release" for call in remote.calls)


def test_publication_path_does_not_require_post_publication_completion_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    called = {"gate": False}

    def forbidden(*_args: object, **_kwargs: object) -> object:
        called["gate"] = True
        raise AssertionError("evaluate_final_publication_gate must not run before publication")

    monkeypatch.setattr(pre_admission, "evaluate_final_publication_gate", forbidden)
    result, _, _ = _publish(tmp_path, monkeypatch)
    assert result["publication"]["state"] == "PUBLISHED"
    assert called["gate"] is False


@pytest.mark.parametrize(
    "boundary",
    ["upload_release_asset", "finalize_release"],
)
def test_campaign_release_reconciles_lost_response_after_remote_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
):
    bundle = _bundle(tmp_path)
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    if boundary == "upload_release_asset":
        remote.seed_admitted_draft(
            repository_slug="owner/repo",
            release_id=ADMITTED_DRAFT_ID,
            tag_name=bundle.version.tag_name,
            target_commitish=SHA,
            assets={},
        )
        write_admitted_release_inventory(tmp_path / "evidence", _inventory_for(bundle))
    else:
        _seed_admitted(remote, bundle, tmp_path / "evidence")
    remote.schedule_failure(boundary, AdapterErrorCategory.UNKNOWN_OUTCOME)
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
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
    assert result["publication"]["state"] == "PUBLISHED"
    assert sum(call[0] == boundary for call in remote.calls) == 1
    with GitHubStewardStore(tmp_path / "evidence" / "release-steward.sqlite3", ROOT) as store:
        assert store.status("owner/repo")["reconciliation_required"] is False


@pytest.mark.parametrize(
    ("boundary", "operation_type"),
    [
        ("upload_release_asset", "UPLOAD_RELEASE_ASSET"),
        ("finalize_release", "FINALIZE_RELEASE"),
    ],
)
def test_campaign_release_recovers_durable_pending_write_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    operation_type: str,
):
    bundle = _bundle(tmp_path)
    from project_pipeline.github_steward.mock import MockGitHubAdapter

    remote = MockGitHubAdapter(repository_slug="owner/repo")
    remote.provider_id = "github-rest"
    if boundary == "upload_release_asset":
        remote.seed_admitted_draft(
            repository_slug="owner/repo",
            release_id=ADMITTED_DRAFT_ID,
            tag_name=bundle.version.tag_name,
            target_commitish=SHA,
            assets={},
        )
        write_admitted_release_inventory(tmp_path / "evidence", _inventory_for(bundle))
    else:
        _seed_admitted(remote, bundle, tmp_path / "evidence")
    persist_applied = draft_release.GitHubDraftReleaseService._persist_applied

    def crash_after_remote_write(self: object, pending: object, *args: object) -> object:
        if getattr(pending.operation_type, "value", "") == operation_type:
            raise RuntimeError("simulated process crash after remote write")
        return persist_applied(self, pending, *args)

    monkeypatch.setattr(
        draft_release.GitHubDraftReleaseService, "_persist_applied", crash_after_remote_write
    )
    _patch_campaign_gate(monkeypatch)
    monkeypatch.setattr(
        release_publication, "build_release_bundle", lambda *_args, **_kwargs: bundle
    )
    with pytest.raises(RuntimeError, match="simulated process crash"):
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
    monkeypatch.setattr(
        draft_release.GitHubDraftReleaseService, "_persist_applied", persist_applied
    )

    with GitHubStewardStore(tmp_path / "evidence" / "release-steward.sqlite3", ROOT) as store:
        assert store.status("owner/repo")["reconciliation_required"] is True
        assert any(
            operation.state.value == "PENDING"
            for operation in store.pending_operations("owner/repo")
        )

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

    assert result["publication"]["state"] == "PUBLISHED"
    assert sum(call[0] == boundary for call in remote.calls) == 1
    with GitHubStewardStore(tmp_path / "evidence" / "release-steward.sqlite3", ROOT) as store:
        assert store.status("owner/repo")["reconciliation_required"] is False
        assert not store.pending_operations("owner/repo")
