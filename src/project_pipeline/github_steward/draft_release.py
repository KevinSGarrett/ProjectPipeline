from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from project_pipeline.contracts import ActionIntent, ApprovalState
from project_pipeline.domain.base import utc_now
from project_pipeline.domain.github import (
    GitHubOperation,
    GitHubOperationReceipt,
    GitHubReleaseAsset,
    GitHubReleaseSnapshot,
    GitOperationState,
    GitOperationType,
    github_identifier,
)
from project_pipeline.github_steward.asset_names import canonical_release_asset_name
from project_pipeline.github_steward.errors import GitHubAdapterError, GitHubStewardError
from project_pipeline.github_steward.persistence import GitHubStewardStore
from project_pipeline.github_steward.ports import GitHubRemotePort, GitHubWriteContext

_CREATE = GitOperationType.CREATE_DRAFT_RELEASE
_UPLOAD = GitOperationType.UPLOAD_RELEASE_ASSET
_FINALIZE = GitOperationType.FINALIZE_RELEASE


def _verify_campaign_publication(
    campaign_database: Path, *, repository_root: Path, campaign_id: str
) -> dict[str, Any]:
    """Resolve the campaign gate at the release-service mutation boundary."""

    # Keep the dependency one-way at import time: the campaign runtime never
    # needs GitHub release infrastructure to start or recover.
    from project_pipeline.autonomy_runtime.campaign import (
        verify_campaign_publication_eligibility,
    )

    return verify_campaign_publication_eligibility(
        campaign_database, repository_root=repository_root, campaign_id=campaign_id
    )


class GitHubDraftReleaseService:
    """Persist-intent GitHub draft-release lifecycle with unknown-outcome recovery."""

    def __init__(self, *, remote: GitHubRemotePort, store: GitHubStewardStore) -> None:
        self.remote = remote
        self.store = store

    def find_draft(
        self, repository_slug: str, *, tag_name: str, target_commitish: str
    ) -> GitHubReleaseSnapshot | None:
        wanted = target_commitish.lower()
        for item in self.remote.list_releases(repository_slug):
            if item.tag_name == tag_name and item.target_commitish.lower() == wanted:
                return item
        return None

    def plan_create_draft(
        self,
        repository_slug: str,
        *,
        tag_name: str,
        name: str,
        body: str,
        target_commitish: str,
        source_tree: str,
        artifact_sha256s: Mapping[str, str],
        actor_id: str,
        correlation_id: str,
    ) -> GitHubOperation:
        self._reject_unknown(_CREATE, repository_slug, tag_name)
        existing = self._existing_tag(repository_slug, tag_name)
        if existing is not None and not existing.draft:
            raise GitHubStewardError("published release already exists for tag")
        if (
            existing is not None
            and existing.draft
            and existing.target_commitish.lower() != target_commitish.lower()
        ):
            raise GitHubStewardError("draft tag is bound to a different candidate head")
        canonical_assets: dict[str, str] = {}
        for raw_name, digest in artifact_sha256s.items():
            asset_name = canonical_release_asset_name(raw_name)
            if asset_name in canonical_assets:
                raise GitHubStewardError("release assets collide after filename normalization")
            canonical_assets[asset_name] = str(digest).lower()
        operation = GitHubOperation.create(
            operation_type=_CREATE,
            repository_slug=repository_slug,
            target=tag_name,
            idempotency_key=(
                f"github.draft.create:{repository_slug}:{tag_name}:{target_commitish.lower()}"
            ),
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload={
                "tag_name": tag_name,
                "name": name,
                "body": body,
                "target_commitish": target_commitish.lower(),
                "source_tree": source_tree.lower(),
                "artifact_sha256s": dict(sorted(canonical_assets.items())),
            },
            expected_head_sha=target_commitish.lower(),
        )
        self.store.save_operation(operation)
        return operation

    def apply_create_draft(
        self,
        operation: GitHubOperation,
        *,
        action_intent: ActionIntent,
        authorization_id: str,
    ) -> GitHubOperationReceipt:
        self._guard_apply(operation, _CREATE, action_intent, "github.draft-release.create")
        pending = self._mark_pending(operation, authorization_id)
        context = self._context(pending, authorization_id)
        try:
            snapshot = self.remote.create_draft_release(
                operation.repository_slug,
                tag_name=str(operation.payload["tag_name"]),
                name=str(operation.payload["name"]),
                body=str(operation.payload.get("body") or ""),
                target_commitish=str(operation.expected_head_sha),
                context=context,
            )
        except GitHubAdapterError as exc:
            return self._persist_error(pending, exc)
        if snapshot.target_commitish.lower() != str(operation.expected_head_sha).lower():
            raise GitHubStewardError("remote draft target_commitish does not match candidate SHA")
        return self._persist_applied(
            pending, snapshot.model_dump(mode="json"), str(snapshot.api_id)
        )

    def reconcile_create_draft(self, operation: GitHubOperation) -> GitHubOperationReceipt:
        stored = self._require_unknown(operation)
        observed = self.find_draft(
            operation.repository_slug,
            tag_name=str(operation.payload["tag_name"]),
            target_commitish=str(operation.expected_head_sha),
        )
        if observed is None:
            failed = stored.model_copy(
                update={
                    "state": GitOperationState.FAILED,
                    "observed_result": {"reconciled": "absent"},
                    "updated_at_utc": utc_now(),
                }
            )
            self.store.save_operation(failed)
            return self._receipt(failed, GitOperationState.FAILED, {"reconciled": "absent"})
        applied = stored.model_copy(
            update={
                "state": GitOperationState.RECONCILED,
                "observed_result": observed.model_dump(mode="json"),
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(applied)
        return self._receipt(
            applied,
            GitOperationState.RECONCILED,
            observed.model_dump(mode="json"),
            str(observed.api_id),
        )

    def plan_upload_asset(
        self,
        repository_slug: str,
        *,
        release_id: int,
        name: str,
        sha256: str,
        source_sha: str,
        actor_id: str,
        correlation_id: str,
    ) -> GitHubOperation:
        canonical_name = canonical_release_asset_name(name)
        release = self._required_release(repository_slug, release_id)
        if not release.draft:
            raise GitHubStewardError("assets may only be uploaded to a draft release")
        if release.target_commitish.lower() != source_sha.lower():
            raise GitHubStewardError("refusing to upload to a release for a different candidate")
        for asset in release.assets:
            if (
                canonical_release_asset_name(asset.name) == canonical_name
                and asset.sha256 != sha256.lower()
            ):
                raise GitHubStewardError("duplicate asset name with a different checksum")
        self._reject_unknown(_UPLOAD, repository_slug, f"{release_id}:{canonical_name}")
        operation = GitHubOperation.create(
            operation_type=_UPLOAD,
            repository_slug=repository_slug,
            target=f"{release_id}:{canonical_name}",
            idempotency_key=(
                f"github.draft.upload:{repository_slug}:{release_id}:{canonical_name}:{sha256.lower()}"
            ),
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload={
                "release_id": release_id,
                "name": canonical_name,
                "sha256": sha256.lower(),
                "source_sha": source_sha.lower(),
            },
            expected_head_sha=source_sha.lower(),
        )
        self.store.save_operation(operation)
        return operation

    def apply_upload_asset(
        self,
        operation: GitHubOperation,
        *,
        content: bytes,
        content_type: str,
        action_intent: ActionIntent,
        authorization_id: str,
    ) -> GitHubOperationReceipt:
        self._guard_apply(operation, _UPLOAD, action_intent, "github.draft-release.upload")
        digest = hashlib.sha256(content).hexdigest()
        expected = str(operation.payload["sha256"]).lower()
        if digest != expected:
            raise GitHubStewardError("upload bytes do not match the planned checksum")
        pending = self._mark_pending(operation, authorization_id)
        context = self._context(pending, authorization_id)
        try:
            asset = self.remote.upload_release_asset(
                operation.repository_slug,
                release_id=int(operation.payload["release_id"]),
                name=str(operation.payload["name"]),
                content=content,
                content_type=content_type,
                context=context,
            )
        except GitHubAdapterError as exc:
            return self._persist_error(pending, exc)
        if asset.sha256 != expected:
            raise GitHubStewardError("uploaded asset checksum diverged from planned bytes")
        return self._persist_applied(pending, asset.model_dump(mode="json"), str(asset.api_id))

    def reconcile_upload_asset(
        self, operation: GitHubOperation, *, content: bytes
    ) -> GitHubOperationReceipt:
        stored = self._require_unknown(operation)
        release = self.remote.get_release(
            operation.repository_slug, int(operation.payload["release_id"])
        )
        name = str(operation.payload["name"])
        expected = str(operation.payload["sha256"]).lower()
        if release is None:
            failed = stored.model_copy(
                update={
                    "state": GitOperationState.FAILED,
                    "observed_result": {"reconciled": "release_absent"},
                    "updated_at_utc": utc_now(),
                }
            )
            self.store.save_operation(failed)
            return self._receipt(failed, GitOperationState.FAILED, {"reconciled": "release_absent"})
        for asset in release.assets:
            if canonical_release_asset_name(asset.name) != name:
                continue
            remote_bytes = self.remote.download_release_asset(
                operation.repository_slug, asset_id=asset.api_id
            )
            digest = hashlib.sha256(remote_bytes).hexdigest()
            if digest != expected or hashlib.sha256(content).hexdigest() != expected:
                raise GitHubStewardError("reconciled asset bytes do not match the planned checksum")
            applied = stored.model_copy(
                update={
                    "state": GitOperationState.RECONCILED,
                    "observed_result": asset.model_dump(mode="json"),
                    "updated_at_utc": utc_now(),
                }
            )
            self.store.save_operation(applied)
            return self._receipt(
                applied,
                GitOperationState.RECONCILED,
                asset.model_dump(mode="json"),
                str(asset.api_id),
            )
        failed = stored.model_copy(
            update={
                "state": GitOperationState.FAILED,
                "observed_result": {"reconciled": "asset_absent"},
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(failed)
        return self._receipt(failed, GitOperationState.FAILED, {"reconciled": "asset_absent"})

    def plan_finalize(
        self,
        repository_slug: str,
        *,
        release_id: int,
        expected_head_sha: str,
        expected_source_tree: str,
        campaign_database: Path,
        campaign_id: str,
        repository_root: Path,
        actor_id: str,
        correlation_id: str,
    ) -> GitHubOperation:
        if self.remote.provider_id != "github-rest":
            raise GitHubStewardError("campaign finalization requires the GitHub REST adapter")
        eligibility = _verify_campaign_publication(
            campaign_database,
            repository_root=repository_root,
            campaign_id=campaign_id,
        )
        if (
            eligibility["integrated_sha"].lower() != expected_head_sha.lower()
            or eligibility["integrated_tree"].lower() != expected_source_tree.lower()
        ):
            raise GitHubStewardError("campaign identity differs from the release candidate")
        release = self._required_release(repository_slug, release_id)
        if release.target_commitish.lower() != expected_head_sha.lower():
            raise GitHubStewardError("changed-head publication is rejected")
        if not release.draft:
            raise GitHubStewardError("release is already published")
        self._reject_unknown(_FINALIZE, repository_slug, str(release_id))
        operation = GitHubOperation.create(
            operation_type=_FINALIZE,
            repository_slug=repository_slug,
            target=str(release_id),
            idempotency_key=(
                f"github.draft.finalize:{repository_slug}:{release_id}:{expected_head_sha.lower()}"
            ),
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload={
                "release_id": release_id,
                "campaign_id": campaign_id,
                "campaign_database": str(campaign_database.resolve()),
                "repository_root": str(repository_root.resolve()),
                "qualification_run_id": eligibility["qualification_run_id"],
                "attested_elapsed_seconds": eligibility["attested_elapsed_seconds"],
                "integrated_tree": eligibility["integrated_tree"],
            },
            expected_head_sha=expected_head_sha.lower(),
        )
        self.store.save_operation(operation)
        return operation

    def apply_finalize(
        self,
        operation: GitHubOperation,
        *,
        action_intent: ActionIntent,
        authorization_id: str,
    ) -> GitHubOperationReceipt:
        stored = self.store.get_operation(operation.operation_id)
        if stored is None:
            raise GitHubStewardError("finalize operation was not persisted")
        self._guard_apply(stored, _FINALIZE, action_intent, "github.draft-release.finalize")
        self._assert_finalize_eligibility(stored)
        pending = self._mark_pending(stored, authorization_id)
        context = self._context(pending, authorization_id)
        try:
            snapshot = self.remote.finalize_release(
                stored.repository_slug,
                release_id=int(stored.payload["release_id"]),
                expected_target_commitish=str(stored.expected_head_sha),
                context=context,
            )
        except GitHubAdapterError as exc:
            return self._persist_error(pending, exc)
        if snapshot.draft:
            raise GitHubStewardError("finalize readback is still draft")
        return self._persist_applied(
            pending, snapshot.model_dump(mode="json"), str(snapshot.api_id)
        )

    def reconcile_finalize(self, operation: GitHubOperation) -> GitHubOperationReceipt:
        """Read back an uncertain finalization before any fresh PATCH attempt."""

        stored = self._require_unknown(operation)
        release = self.remote.get_release(stored.repository_slug, int(stored.payload["release_id"]))
        if (
            release is not None
            and release.target_commitish.lower() == str(stored.expected_head_sha).lower()
            and not release.draft
        ):
            reconciled = stored.model_copy(
                update={
                    "state": GitOperationState.RECONCILED,
                    "observed_result": release.model_dump(mode="json"),
                    "updated_at_utc": utc_now(),
                }
            )
            self.store.save_operation(reconciled)
            return self._receipt(
                reconciled,
                GitOperationState.RECONCILED,
                release.model_dump(mode="json"),
                str(release.api_id),
            )
        failed = stored.model_copy(
            update={
                "state": GitOperationState.FAILED,
                "observed_result": {
                    "reconciled": "release_absent_or_still_draft",
                    "release_id": stored.payload["release_id"],
                },
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(failed)
        return self._receipt(failed, GitOperationState.FAILED, dict(failed.observed_result or {}))

    def acquire_assets(
        self,
        repository_slug: str,
        *,
        release_id: int,
        expected_sha256s: Mapping[str, str],
        expected_head_sha: str,
    ) -> dict[str, bytes]:
        release = self._required_release(repository_slug, release_id)
        if release.target_commitish.lower() != expected_head_sha.lower():
            raise GitHubStewardError("acquired release is bound to a different candidate")
        expected: dict[str, str] = {}
        for raw_name, digest in expected_sha256s.items():
            name = canonical_release_asset_name(raw_name)
            if name in expected:
                raise GitHubStewardError(
                    "expected asset names collide after filename normalization"
                )
            expected[name] = digest.lower()
        observed: dict[str, GitHubReleaseAsset] = {}
        for asset in release.assets:
            name = canonical_release_asset_name(asset.name)
            if name in observed:
                raise GitHubStewardError(
                    "remote release assets collide after filename normalization"
                )
            observed[name] = asset
        if set(observed) != set(expected):
            raise GitHubStewardError("acquired asset set does not match the candidate manifest")
        payload: dict[str, bytes] = {}
        for name, asset in observed.items():
            content = self.remote.download_release_asset(repository_slug, asset_id=asset.api_id)
            digest = hashlib.sha256(content).hexdigest()
            if digest != expected[name]:
                raise GitHubStewardError(f"acquired asset {name} checksum mismatch")
            payload[name] = content
        return payload

    def _assert_finalize_eligibility(self, operation: GitHubOperation) -> None:
        """Re-attest campaign and remote draft immediately before finalization."""

        if self.remote.provider_id != "github-rest":
            raise GitHubStewardError("campaign finalization requires the GitHub REST adapter")
        try:
            database = Path(str(operation.payload["campaign_database"]))
            root = Path(str(operation.payload["repository_root"]))
            campaign_id = str(operation.payload["campaign_id"])
        except KeyError as exc:
            raise GitHubStewardError("finalize operation lacks immutable campaign binding") from exc
        eligibility = _verify_campaign_publication(
            database, repository_root=root, campaign_id=campaign_id
        )
        if (
            eligibility["integrated_sha"].lower() != str(operation.expected_head_sha).lower()
            or eligibility["integrated_tree"].lower()
            != str(operation.payload["integrated_tree"]).lower()
            or eligibility["qualification_run_id"] != operation.payload["qualification_run_id"]
            or float(eligibility["attested_elapsed_seconds"])
            != float(operation.payload["attested_elapsed_seconds"])
        ):
            raise GitHubStewardError("campaign attestation changed after finalization was planned")
        release = self._required_release(
            operation.repository_slug, int(operation.payload["release_id"])
        )
        if release.target_commitish.lower() != str(operation.expected_head_sha).lower():
            raise GitHubStewardError("changed-head publication is rejected")
        if not release.draft:
            raise GitHubStewardError("release is already published")

    def _existing_tag(self, repository_slug: str, tag_name: str) -> GitHubReleaseSnapshot | None:
        for item in self.remote.list_releases(repository_slug):
            if item.tag_name == tag_name:
                return item
        return None

    def _required_release(self, repository_slug: str, release_id: int) -> GitHubReleaseSnapshot:
        release = self.remote.get_release(repository_slug, release_id)
        if release is None:
            raise GitHubStewardError(f"release not found: {repository_slug}#{release_id}")
        return release

    def _reject_unknown(
        self, operation_type: GitOperationType, repository_slug: str, target: str
    ) -> None:
        for pending in self.store.pending_operations(repository_slug):
            if (
                pending.operation_type is operation_type
                and pending.target == target
                and pending.state in {GitOperationState.PENDING, GitOperationState.UNKNOWN_OUTCOME}
            ):
                raise GitHubStewardError(
                    "pending or unknown-outcome operations must be reconciled before any retry"
                )

    def _guard_apply(
        self,
        operation: GitHubOperation,
        expected: GitOperationType,
        action_intent: ActionIntent,
        operation_name: str,
    ) -> None:
        stored = self.store.get_operation(operation.operation_id)
        if stored is not None and stored.state in {
            GitOperationState.PENDING,
            GitOperationState.UNKNOWN_OUTCOME,
        }:
            raise GitHubStewardError(
                "pending or unknown-outcome operations must be reconciled before any retry"
            )
        if operation.operation_type is not expected:
            raise GitHubStewardError("operation type mismatch")
        if action_intent.approval_state is not ApprovalState.APPROVED:
            raise GitHubStewardError("action intent is not approved")
        if (
            action_intent.authority != "github.steward"
            or action_intent.target != operation.repository_slug
            or action_intent.operation != operation_name
        ):
            raise GitHubStewardError(
                "action intent does not authorize the requested GitHub operation"
            )

    def _mark_pending(self, operation: GitHubOperation, authorization_id: str) -> GitHubOperation:
        pending = operation.model_copy(
            update={
                "state": GitOperationState.PENDING,
                "authorization_id": authorization_id,
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(pending)
        return pending

    @staticmethod
    def _context(operation: GitHubOperation, authorization_id: str) -> GitHubWriteContext:
        return GitHubWriteContext(
            actor_id=operation.actor_id,
            correlation_id=operation.correlation_id,
            idempotency_key=operation.idempotency_key,
            authorization_id=authorization_id,
            expected_head_sha=operation.expected_head_sha,
        )

    def _persist_error(
        self, pending: GitHubOperation, exc: GitHubAdapterError
    ) -> GitHubOperationReceipt:
        state = (
            GitOperationState.UNKNOWN_OUTCOME
            if exc.payload.unknown_outcome
            else GitOperationState.FAILED
        )
        observed = {"error": exc.payload.model_dump(mode="json")}
        failed = pending.model_copy(
            update={"state": state, "observed_result": observed, "updated_at_utc": utc_now()}
        )
        self.store.save_operation(failed)
        return self._receipt(
            failed,
            state,
            observed,
            exc.payload.external_operation_id,
            reconciliation_required=state is GitOperationState.UNKNOWN_OUTCOME,
        )

    def _persist_applied(
        self, pending: GitHubOperation, observed: dict[str, Any], external_id: str
    ) -> GitHubOperationReceipt:
        applied = pending.model_copy(
            update={
                "state": GitOperationState.APPLIED,
                "observed_result": observed,
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(applied)
        return self._receipt(applied, GitOperationState.APPLIED, observed, external_id)

    def _require_unknown(self, operation: GitHubOperation) -> GitHubOperation:
        stored = self.store.get_operation(operation.operation_id)
        if stored is None:
            raise GitHubStewardError("operation is not persisted")
        if stored.state is not GitOperationState.UNKNOWN_OUTCOME:
            raise GitHubStewardError("operation is not awaiting unknown-outcome reconciliation")
        return stored

    def _receipt(
        self,
        operation: GitHubOperation,
        state: GitOperationState,
        observed: dict[str, Any],
        external_id: str | None = None,
        *,
        reconciliation_required: bool = False,
    ) -> GitHubOperationReceipt:
        receipt = GitHubOperationReceipt(
            receipt_id=github_identifier("GHREC", operation.operation_id, state.value),
            operation_id=operation.operation_id,
            state=state,
            provider=self.remote.provider_id,
            external_identifier=external_id,
            observed_result=observed,
            reconciliation_required=reconciliation_required,
        )
        self.store.save_receipt(receipt)
        return receipt


def bound_asset(name: str, content: bytes, *, api_id: int, content_type: str) -> GitHubReleaseAsset:
    digest = hashlib.sha256(content).hexdigest()
    return GitHubReleaseAsset(
        asset_id=github_identifier("GHREL", "asset", name, digest),
        api_id=api_id,
        name=name,
        sha256=digest,
        size_bytes=len(content),
        content_type=content_type,
    )
