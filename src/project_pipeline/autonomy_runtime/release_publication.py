"""Campaign-bound remote release publication with byte-level reconciliation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.campaign import verify_campaign_publication_eligibility
from project_pipeline.contracts import ActionIntent, ApprovalState, RiskLevel
from project_pipeline.github_steward.draft_release import GitHubDraftReleaseService
from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.github_steward.persistence import GitHubStewardStore
from project_pipeline.github_steward.ports import GitHubRemotePort
from project_pipeline.release_factory.bundle import artifact_sha256s, build_release_bundle
from project_pipeline.release_factory.lifecycle import write_acquired_assets


def _intent(
    *,
    repository_slug: str,
    operation: str,
    idempotency_key: str,
    actor_id: str,
    correlation_id: str,
) -> ActionIntent:
    return ActionIntent(
        actor_id=actor_id,
        authority="github.steward",
        target=repository_slug,
        operation=operation,
        idempotency_key=idempotency_key,
        approval_state=ApprovalState.APPROVED,
        correlation_id=correlation_id,
        risk=RiskLevel.HIGH,
    )


def _require_applied(receipt: Any, *, operation: str) -> int:
    if receipt.state.value not in {"APPLIED", "RECONCILED"}:
        raise GitHubStewardError(f"remote {operation} did not produce an applied receipt")
    if not receipt.external_identifier:
        raise GitHubStewardError(f"remote {operation} receipt omitted its external identifier")
    return int(receipt.external_identifier)


def publish_campaign_release(
    *,
    repository_root: Path,
    campaign_database: Path,
    campaign_id: str,
    evidence_path: Path,
    repository_slug: str,
    remote: GitHubRemotePort,
    actor_id: str,
    authorization_id: str,
    correlation_id: str,
    desktop_artifact_dir: Path | None = None,
    fixture_desktop: bool = False,
) -> dict[str, Any]:
    """Create/fill/finalize one candidate-bound draft and verify remote bytes.

    The caller cannot replace campaign qualification with an approval flag: this
    function first validates the persisted 72-hour attestation and exact Git
    identity.  A release is reported as published only after every asset has
    been downloaded from the remote release and rehashed after finalization.
    """

    root = repository_root.resolve()
    evidence = evidence_path.resolve()
    eligibility = verify_campaign_publication_eligibility(
        campaign_database, repository_root=root, campaign_id=campaign_id
    )
    bundle = build_release_bundle(
        root,
        evidence / "release-bundle",
        desktop_artifact_dir=desktop_artifact_dir,
        fixture_desktop=fixture_desktop,
    )
    if (
        bundle.version.source_sha != eligibility["integrated_sha"]
        or bundle.version.source_tree != eligibility["integrated_tree"]
    ):
        raise GitHubStewardError("release bundle identity differs from the attested campaign")
    if remote.provider_id != "github-rest":
        raise GitHubStewardError("campaign publication requires the GitHub REST adapter")
    if fixture_desktop:
        raise GitHubStewardError("fixture desktop artifacts are test-only and cannot be published")
    if not bundle.desktop_bound and not fixture_desktop:
        raise GitHubStewardError("release publication requires real bound desktop artifacts")
    expected_assets = artifact_sha256s(bundle)
    if not expected_assets:
        raise GitHubStewardError("release publication requires bound release artifacts")

    evidence.mkdir(parents=True, exist_ok=True)
    store_path = evidence / "release-steward.sqlite3"
    with GitHubStewardStore(store_path, root) as store:
        service = GitHubDraftReleaseService(remote=remote, store=store)
        release = service.find_draft(
            repository_slug,
            tag_name=bundle.version.tag_name,
            target_commitish=bundle.version.source_sha,
        )
        if release is None:
            planned = service.plan_create_draft(
                repository_slug,
                tag_name=bundle.version.tag_name,
                name=f"ProjectPipeline {bundle.version.bundle_version} draft",
                body="Campaign-bound draft candidate. Publication requires 72-hour attestation.",
                target_commitish=bundle.version.source_sha,
                source_tree=bundle.version.source_tree,
                artifact_sha256s=expected_assets,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            receipt = service.apply_create_draft(
                planned,
                action_intent=_intent(
                    repository_slug=repository_slug,
                    operation="github.draft-release.create",
                    idempotency_key=planned.idempotency_key,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                ),
                authorization_id=authorization_id,
            )
            release_id = _require_applied(receipt, operation="draft creation")
            release = remote.get_release(repository_slug, release_id)
        if release is None:
            raise GitHubStewardError("draft release readback is absent")
        if not release.draft or release.target_commitish.lower() != bundle.version.source_sha:
            raise GitHubStewardError("draft release is not bound to the campaign candidate")

        existing_assets = {asset.name: asset for asset in release.assets}
        for artifact in bundle.artifacts:
            if not artifact.bound:
                continue
            existing = existing_assets.get(artifact.name)
            if existing is not None:
                if existing.sha256 != artifact.sha256:
                    raise GitHubStewardError("remote draft contains an asset with divergent bytes")
                continue
            payload = (Path(bundle.output_dir) / artifact.name).read_bytes()
            operation = service.plan_upload_asset(
                repository_slug,
                release_id=release.api_id,
                name=artifact.name,
                sha256=artifact.sha256,
                source_sha=bundle.version.source_sha,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            receipt = service.apply_upload_asset(
                operation,
                content=payload,
                content_type="application/octet-stream",
                action_intent=_intent(
                    repository_slug=repository_slug,
                    operation="github.draft-release.upload",
                    idempotency_key=operation.idempotency_key,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                ),
                authorization_id=authorization_id,
            )
            _require_applied(receipt, operation=f"asset upload {artifact.name}")

        release = remote.get_release(repository_slug, release.api_id)
        if release is None or not release.draft:
            raise GitHubStewardError("draft release disappeared before finalization")
        draft_bytes = service.acquire_assets(
            repository_slug,
            release_id=release.api_id,
            expected_sha256s=expected_assets,
            expected_head_sha=bundle.version.source_sha,
        )
        finalize = service.plan_finalize(
            repository_slug,
            release_id=release.api_id,
            expected_head_sha=bundle.version.source_sha,
            expected_source_tree=bundle.version.source_tree,
            campaign_database=campaign_database,
            campaign_id=campaign_id,
            repository_root=root,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        receipt = service.apply_finalize(
            finalize,
            action_intent=_intent(
                repository_slug=repository_slug,
                operation="github.draft-release.finalize",
                idempotency_key=finalize.idempotency_key,
                actor_id=actor_id,
                correlation_id=correlation_id,
            ),
            authorization_id=authorization_id,
        )
        _require_applied(receipt, operation="draft finalization")
        final_release = remote.get_release(repository_slug, release.api_id)
        if final_release is None or final_release.draft:
            raise GitHubStewardError("published release readback is absent or still a draft")
        if final_release.target_commitish.lower() != bundle.version.source_sha:
            raise GitHubStewardError("published release target differs from the campaign candidate")
        remote_bytes = service.acquire_assets(
            repository_slug,
            release_id=final_release.api_id,
            expected_sha256s=expected_assets,
            expected_head_sha=bundle.version.source_sha,
        )
        if remote_bytes != draft_bytes:
            raise GitHubStewardError("published release bytes differ from the verified draft bytes")
        acquired_path = write_acquired_assets(evidence / "remote-acquired", remote_bytes)
        remote_assets = {asset.name: asset for asset in final_release.assets}
        assets = [
            {
                "name": name,
                "sha256": digest,
                "remote_sha256": hashlib.sha256(remote_bytes[name]).hexdigest(),
                "asset_id": remote_assets[name].api_id,
                "bytes_verified": True,
            }
            for name, digest in sorted(expected_assets.items())
        ]
        (acquired_path / "campaign_publication.json").write_text(
            json.dumps(
                {
                    "state": "PUBLISHED",
                    "provider": remote.provider_id,
                    "release_id": final_release.api_id,
                    "tag_name": final_release.tag_name,
                    "source_sha": bundle.version.source_sha,
                    "source_tree": bundle.version.source_tree,
                    "assets": assets,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return {
        "publication": {
            "state": "PUBLISHED",
            "draft": False,
            "release_id": final_release.api_id,
            "tag_name": final_release.tag_name,
            "target_commitish": bundle.version.source_sha,
            "source_tree": bundle.version.source_tree,
            "provider": remote.provider_id,
            "fixture_desktop": False,
            "assets": assets,
            "acquired_path": str(acquired_path),
        },
        "campaign": eligibility,
        "user_action_required": False,
    }
