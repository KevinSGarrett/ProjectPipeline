"""Campaign-bound remote release publication with byte-level reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.admitted_release import (
    admitted_asset_sha256s,
    load_admitted_release_inventory,
)
from project_pipeline.autonomy_runtime.campaign import verify_campaign_publication_eligibility
from project_pipeline.contracts import ActionIntent, ApprovalState, RiskLevel
from project_pipeline.github_steward.asset_names import canonical_release_asset_name
from project_pipeline.github_steward.draft_release import GitHubDraftReleaseService
from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.github_steward.persistence import GitHubStewardStore
from project_pipeline.github_steward.ports import GitHubRemotePort
from project_pipeline.release_factory.bundle import artifact_sha256s, build_release_bundle
from project_pipeline.release_factory.lifecycle import candidate_acquired_dir, write_acquired_assets


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


def _settle_write(
    receipt: Any,
    *,
    operation: str,
    reconcile: Callable[[], Any],
    retry_after_readback: Callable[[], Any],
) -> Any:
    """Reconcile a lost response before one fresh, readback-authorized retry."""

    if not receipt.reconciliation_required:
        return receipt
    reconciled = reconcile()
    if reconciled.state.value in {"APPLIED", "RECONCILED"}:
        return reconciled
    if reconciled.state.value != "FAILED":
        return reconciled
    retried = retry_after_readback()
    if retried.reconciliation_required:
        retried = reconcile()
    return retried


def _artifact_payloads(bundle: Any) -> dict[str, bytes]:
    output = Path(bundle.output_dir)
    payloads: dict[str, bytes] = {}
    for artifact in bundle.artifacts:
        if not artifact.bound:
            continue
        name = canonical_release_asset_name(artifact.name)
        candidates = [output / name]
        if artifact.name != name:
            candidates.append(output / artifact.name)
        local = next((path for path in candidates if path.is_file()), None)
        if local is None:
            raise GitHubStewardError(f"release bundle artifact is missing: {name}")
        if name in payloads:
            raise GitHubStewardError("release bundle assets collide after filename normalization")
        payloads[name] = local.read_bytes()
    return payloads


def _reconcile_interrupted_writes(
    service: GitHubDraftReleaseService,
    *,
    repository_slug: str,
    bundle: Any,
    artifact_payloads: dict[str, bytes],
    campaign_id: str,
) -> None:
    """Resolve a prior process crash before observing or issuing new writes."""

    for operation in service.store.pending_operations(repository_slug):
        if operation.state.value == "PENDING":
            operation = service.store.mark_interrupted_pending_unknown(operation)
        if operation.state.value != "UNKNOWN_OUTCOME":
            continue
        if operation.expected_head_sha != bundle.version.source_sha:
            continue
        if operation.operation_type.value == "CREATE_DRAFT_RELEASE":
            if operation.payload.get("tag_name") == bundle.version.tag_name:
                service.reconcile_create_draft(operation)
        elif operation.operation_type.value == "UPLOAD_RELEASE_ASSET":
            name = canonical_release_asset_name(str(operation.payload.get("name") or ""))
            if name in artifact_payloads:
                service.reconcile_upload_asset(operation, content=artifact_payloads[name])
        elif (
            operation.operation_type.value == "FINALIZE_RELEASE"
            and operation.payload.get("campaign_id") == campaign_id
        ):
            service.reconcile_finalize(operation)


def _write_publication_binding(acquired_path: Path, payload: dict[str, Any]) -> None:
    binding_path = acquired_path / "campaign_publication.json"
    if binding_path.exists():
        try:
            existing = json.loads(binding_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GitHubStewardError("acquired publication binding is malformed") from exc
        if existing != payload:
            raise GitHubStewardError("candidate-scoped acquired publication binding is immutable")
        return
    binding_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_admitted_draft(
    remote: GitHubRemotePort,
    *,
    repository_slug: str,
    inventory: dict[str, Any],
    source_sha: str,
    source_tree: str,
    tag_name: str,
) -> Any:
    """Pin finalization to the originally admitted draft identity."""

    if (
        inventory["source_sha"] != source_sha.lower()
        or inventory["source_tree"] != source_tree.lower()
        or inventory["target_commitish"] != source_sha.lower()
        or inventory["tag_name"] != tag_name
    ):
        raise GitHubStewardError("admitted draft tag/target differs from the attested candidate")
    release = remote.get_release(repository_slug, int(inventory["draft_id"]))
    if release is None:
        raise GitHubStewardError("admitted draft identity is missing")
    if int(release.api_id) != int(inventory["draft_id"]):
        raise GitHubStewardError("admitted draft identity was substituted")
    if release.tag_name != tag_name:
        raise GitHubStewardError("admitted draft tag changed")
    if release.target_commitish.lower() != source_sha.lower():
        raise GitHubStewardError("admitted draft target differs from the campaign candidate")
    return release


def _assert_bundle_matches_admitted(bundle: Any, inventory: dict[str, Any]) -> dict[str, str]:
    expected = admitted_asset_sha256s(inventory)
    expected_sizes = {str(item["name"]): int(item["size_bytes"]) for item in inventory["assets"]}
    observed = artifact_sha256s(bundle)
    if set(observed) != set(expected):
        raise GitHubStewardError("bundle asset set diverges from the admitted inventory")
    for name, digest in expected.items():
        artifact = next(
            item
            for item in bundle.artifacts
            if item.bound and canonical_release_asset_name(item.name) == name
        )
        if artifact.sha256 != digest or int(artifact.size_bytes) != expected_sizes[name]:
            raise GitHubStewardError("changed bytes at the same source SHA/tree")
        if observed[name] != digest:
            raise GitHubStewardError("changed bytes at the same source SHA/tree")
    return expected


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
    """Finalize the originally admitted draft and verify remote bytes.

    The caller cannot replace campaign qualification with an approval flag: this
    function first validates the persisted 72-hour attestation, exact Git
    identity, and the immutable admitted draft/asset inventory. A rebuild or
    cache miss may proceed only when every byte still matches that inventory.
    A release is reported as published only after every asset has been
    downloaded from that same draft identity and rehashed after finalization.
    """

    root = repository_root.resolve()
    evidence = evidence_path.resolve()
    inventory = load_admitted_release_inventory(evidence)
    eligibility = verify_campaign_publication_eligibility(
        campaign_database, repository_root=root, campaign_id=campaign_id
    )
    if (
        inventory["source_sha"] != str(eligibility["integrated_sha"]).lower()
        or inventory["source_tree"] != str(eligibility["integrated_tree"]).lower()
    ):
        raise GitHubStewardError("admitted inventory is not bound to the attested campaign")
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
    expected_assets = _assert_bundle_matches_admitted(bundle, inventory)
    local_payloads = _artifact_payloads(bundle)
    if {name: hashlib.sha256(payload).hexdigest() for name, payload in local_payloads.items()} != (
        expected_assets
    ):
        raise GitHubStewardError("release bundle bytes differ from its canonical asset manifest")
    for name, digest in expected_assets.items():
        if name not in local_payloads:
            raise GitHubStewardError("admitted asset is missing from the local bundle cache")
        payload = local_payloads[name]
        if hashlib.sha256(payload).hexdigest() != digest or len(payload) != next(
            int(item["size_bytes"]) for item in inventory["assets"] if item["name"] == name
        ):
            raise GitHubStewardError("changed bytes at the same source SHA/tree")

    evidence.mkdir(parents=True, exist_ok=True)
    store_path = evidence / "release-steward.sqlite3"
    with GitHubStewardStore(store_path, root) as store:
        service = GitHubDraftReleaseService(remote=remote, store=store)
        _reconcile_interrupted_writes(
            service,
            repository_slug=repository_slug,
            bundle=bundle,
            artifact_payloads=local_payloads,
            campaign_id=campaign_id,
        )
        release = _require_admitted_draft(
            remote,
            repository_slug=repository_slug,
            inventory=inventory,
            source_sha=bundle.version.source_sha,
            source_tree=bundle.version.source_tree,
            tag_name=bundle.version.tag_name,
        )
        listed = service.find_draft(
            repository_slug,
            tag_name=bundle.version.tag_name,
            target_commitish=bundle.version.source_sha,
        )
        if listed is not None and int(listed.api_id) != int(inventory["draft_id"]):
            raise GitHubStewardError("admitted draft identity was substituted")
        release_id = release.api_id

        existing_assets = {
            canonical_release_asset_name(asset.name): asset for asset in release.assets
        }
        if len(existing_assets) != len(release.assets):
            raise GitHubStewardError("remote draft assets collide after filename normalization")
        extra_assets = set(existing_assets) - set(expected_assets)
        if extra_assets:
            raise GitHubStewardError("remote draft contains extra assets")
        for artifact in bundle.artifacts:
            if not artifact.bound:
                continue
            name = canonical_release_asset_name(artifact.name)
            existing = existing_assets.get(name)
            if existing is not None:
                if existing.sha256 != artifact.sha256 or int(existing.size_bytes) != int(
                    artifact.size_bytes
                ):
                    raise GitHubStewardError("remote draft contains an asset with divergent bytes")
                continue
            if not release.draft:
                raise GitHubStewardError("published release is missing a candidate artifact")
            payload = local_payloads[name]
            operation = service.plan_upload_asset(
                repository_slug,
                release_id=release_id,
                name=name,
                sha256=artifact.sha256,
                source_sha=bundle.version.source_sha,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )

            def apply_upload(operation: Any = operation, payload: bytes = payload) -> Any:
                return service.apply_upload_asset(
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

            def retry_upload(
                name: str = name,
                artifact: Any = artifact,
                payload: bytes = payload,
            ) -> Any:
                retry = service.plan_upload_asset(
                    repository_slug,
                    release_id=release_id,
                    name=name,
                    sha256=artifact.sha256,
                    source_sha=bundle.version.source_sha,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                )
                return service.apply_upload_asset(
                    retry,
                    content=payload,
                    content_type="application/octet-stream",
                    action_intent=_intent(
                        repository_slug=repository_slug,
                        operation="github.draft-release.upload",
                        idempotency_key=retry.idempotency_key,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                    ),
                    authorization_id=authorization_id,
                )

            def reconcile_upload(operation: Any = operation, payload: bytes = payload) -> Any:
                return service.reconcile_upload_asset(operation, content=payload)

            receipt = _settle_write(
                apply_upload(),
                operation=f"asset upload {name}",
                reconcile=reconcile_upload,
                retry_after_readback=retry_upload,
            )
            _require_applied(receipt, operation=f"asset upload {name}")

        release = remote.get_release(repository_slug, release_id)
        if release is None:
            raise GitHubStewardError("release disappeared before finalization")
        draft_bytes = service.acquire_assets(
            repository_slug,
            release_id=release_id,
            expected_sha256s=expected_assets,
            expected_head_sha=bundle.version.source_sha,
        )
        if release.draft:
            finalize = service.plan_finalize(
                repository_slug,
                release_id=release_id,
                expected_head_sha=bundle.version.source_sha,
                expected_source_tree=bundle.version.source_tree,
                campaign_database=campaign_database,
                campaign_id=campaign_id,
                repository_root=root,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )

            def apply_finalize() -> Any:
                return service.apply_finalize(
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

            def retry_finalize() -> Any:
                retry = service.plan_finalize(
                    repository_slug,
                    release_id=release_id,
                    expected_head_sha=bundle.version.source_sha,
                    expected_source_tree=bundle.version.source_tree,
                    campaign_database=campaign_database,
                    campaign_id=campaign_id,
                    repository_root=root,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                )
                return service.apply_finalize(
                    retry,
                    action_intent=_intent(
                        repository_slug=repository_slug,
                        operation="github.draft-release.finalize",
                        idempotency_key=retry.idempotency_key,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                    ),
                    authorization_id=authorization_id,
                )

            receipt = _settle_write(
                apply_finalize(),
                operation="draft finalization",
                reconcile=lambda: service.reconcile_finalize(finalize),
                retry_after_readback=retry_finalize,
            )
            _require_applied(receipt, operation="draft finalization")
        final_release = remote.get_release(repository_slug, release_id)
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
        acquired_path = write_acquired_assets(
            candidate_acquired_dir(
                evidence,
                source_sha=bundle.version.source_sha,
                source_tree=bundle.version.source_tree,
            ),
            remote_bytes,
        )
        remote_assets = {
            canonical_release_asset_name(asset.name): asset for asset in final_release.assets
        }
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
        _write_publication_binding(
            acquired_path,
            {
                "state": "PUBLISHED",
                "provider": remote.provider_id,
                "release_id": final_release.api_id,
                "tag_name": final_release.tag_name,
                "source_sha": bundle.version.source_sha,
                "source_tree": bundle.version.source_tree,
                "assets": assets,
            },
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
