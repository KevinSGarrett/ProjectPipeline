from __future__ import annotations

import hashlib
import json
from typing import Any

from project_pipeline.contracts import ActionIntent, ApprovalState
from project_pipeline.domain.base import utc_now
from project_pipeline.domain.github import (
    AutonomousReviewReceipt,
    GitHubOperation,
    GitHubOperationReceipt,
    GitOperationState,
    GitOperationType,
    LifecycleRecord,
    LifecycleStep,
    MergeGateState,
    PullRequestState,
    github_identifier,
)
from project_pipeline.github_steward.autonomous_review import evaluate_autonomous_review
from project_pipeline.github_steward.errors import GitHubAdapterError, GitHubStewardError
from project_pipeline.github_steward.merge_gate import evaluate_merge_gate
from project_pipeline.github_steward.persistence import GitHubStewardStore
from project_pipeline.github_steward.ports import GitHubRemotePort, GitHubWriteContext
from project_pipeline.github_steward.protection_drift import evaluate_protection_drift


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ClosedLoopLifecycle:
    def __init__(
        self,
        *,
        remote: GitHubRemotePort,
        store: GitHubStewardStore,
        repository_slug: str,
    ) -> None:
        self.remote = remote
        self.store = store
        self.repository_slug = repository_slug

    def persist_intent(
        self,
        *,
        operation_type: GitOperationType,
        target: str,
        actor_id: str,
        correlation_id: str,
        payload: dict[str, Any],
        expected_head_sha: str | None = None,
    ) -> GitHubOperation:
        operation = GitHubOperation.create(
            operation_type=operation_type,
            repository_slug=self.repository_slug,
            target=target,
            idempotency_key=f"lifecycle:{operation_type.value}:{self.repository_slug}:{target}:{expected_head_sha or 'none'}",
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload=payload,
            expected_head_sha=expected_head_sha,
        )
        existing = self.store.get_operation(operation.operation_id)
        if existing is not None:
            return existing
        self.store.save_operation(operation)
        return operation

    def readback_pull(self, number: int) -> dict[str, Any]:
        pull = self.remote.get_pull_request(self.repository_slug, number)
        if pull is None:
            return {"found": False, "number": number}
        return {
            "found": True,
            "number": pull.number,
            "state": pull.state.value,
            "head_sha": pull.head_sha,
            "draft": pull.draft,
            "mergeable": pull.mergeable,
        }

    def apply_step(
        self,
        operation: GitHubOperation,
        *,
        action_intent: ActionIntent,
        authorization_id: str,
        apply: bool,
    ) -> GitHubOperationReceipt:
        if action_intent.approval_state is not ApprovalState.APPROVED:
            raise GitHubStewardError("action intent is not approved")
        current = self.store.get_operation(operation.operation_id)
        if current is not None and current.state is GitOperationState.UNKNOWN_OUTCOME:
            raise GitHubStewardError(
                "unknown-outcome operations must be reconciled before any retry"
            )
        if operation.operation_type is GitOperationType.MERGE_PULL_REQUEST:
            ready = self.evaluate_ready(
                int(operation.target),
                expected_head_sha=str(operation.expected_head_sha),
                review=(
                    AutonomousReviewReceipt.model_validate(operation.payload["receipt"])
                    if operation.payload.get("receipt")
                    else None
                ),
                required_checks=tuple(operation.payload.get("required_checks") or ()),
            )
            if not ready["ready"]:
                raise GitHubStewardError(
                    f"Merge Gate is blocked: {ready['gate'].get('blockers')}"
                )
        if not apply:
            return GitHubOperationReceipt(
                receipt_id=github_identifier("GHREC", operation.operation_id, "PLANNED"),
                operation_id=operation.operation_id,
                state=GitOperationState.PLANNED,
                provider=self.remote.provider_id,
                observed_result={"mode": "DRY_RUN"},
            )
        pending = operation.model_copy(
            update={
                "state": GitOperationState.PENDING,
                "authorization_id": authorization_id,
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(pending)
        context = GitHubWriteContext(
            actor_id=operation.actor_id,
            correlation_id=operation.correlation_id,
            idempotency_key=operation.idempotency_key,
            authorization_id=authorization_id,
            expected_head_sha=operation.expected_head_sha,
        )
        try:
            observed = self._dispatch(operation, context)
        except GitHubAdapterError as exc:
            state = (
                GitOperationState.UNKNOWN_OUTCOME
                if exc.payload.unknown_outcome
                else GitOperationState.FAILED
            )
            failed = pending.model_copy(
                update={
                    "state": state,
                    "observed_result": {"error": exc.payload.model_dump(mode="json")},
                    "updated_at_utc": utc_now(),
                }
            )
            self.store.save_operation(failed)
            receipt = GitHubOperationReceipt(
                receipt_id=github_identifier("GHREC", operation.operation_id, state.value),
                operation_id=operation.operation_id,
                state=state,
                provider=self.remote.provider_id,
                external_identifier=exc.payload.external_operation_id,
                observed_result=failed.observed_result,
                reconciliation_required=state is GitOperationState.UNKNOWN_OUTCOME,
            )
            self.store.save_receipt(receipt)
            return receipt
        applied = pending.model_copy(
            update={
                "state": GitOperationState.APPLIED,
                "observed_result": dict(observed),
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(applied)
        receipt = GitHubOperationReceipt(
            receipt_id=github_identifier("GHREC", operation.operation_id, "APPLIED"),
            operation_id=operation.operation_id,
            state=GitOperationState.APPLIED,
            provider=self.remote.provider_id,
            external_identifier=str(observed.get("external_identifier") or "") or None,
            observed_result=dict(observed),
        )
        self.store.save_receipt(receipt)
        return receipt

    def reconcile_unknown(self, operation: GitHubOperation) -> GitHubOperation:
        if operation.state is not GitOperationState.UNKNOWN_OUTCOME:
            return operation
        if operation.operation_type is GitOperationType.MERGE_PULL_REQUEST:
            readback = self.readback_pull(int(operation.target))
            if readback.get("state") == PullRequestState.MERGED.value:
                reconciled = operation.model_copy(
                    update={
                        "state": GitOperationState.RECONCILED,
                        "observed_result": readback,
                        "updated_at_utc": utc_now(),
                    }
                )
                self.store.save_operation(reconciled)
                return reconciled
        if operation.operation_type is GitOperationType.DELETE_BRANCH:
            remaining = {item.name for item in self.remote.iter_branches(self.repository_slug)}
            if operation.target not in remaining:
                reconciled = operation.model_copy(
                    update={
                        "state": GitOperationState.RECONCILED,
                        "observed_result": {"deleted": operation.target, "still_present": False},
                        "updated_at_utc": utc_now(),
                    }
                )
                self.store.save_operation(reconciled)
                return reconciled
        return operation

    def evaluate_ready(
        self,
        number: int,
        *,
        expected_head_sha: str,
        review: AutonomousReviewReceipt | None = None,
        required_checks: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        pull = self.remote.get_pull_request(self.repository_slug, number)
        if pull is None:
            raise GitHubStewardError(f"pull request not found: {number}")
        reviews = tuple(self.remote.iter_reviews(self.repository_slug, number))
        checks = tuple(self.remote.iter_checks(self.repository_slug, pull.head_sha))
        snapshot = pull.model_copy(update={"reviews": reviews, "checks": checks})
        protection = self.remote.get_branch_protection(self.repository_slug, snapshot.base_branch)
        drift = evaluate_protection_drift(protection)
        gate = evaluate_merge_gate(
            snapshot,
            required_checks=required_checks or protection.required_status_checks,
            approvals_required=protection.required_approving_review_count,
            require_head_sha=expected_head_sha,
            autonomous_review=review,
            protection_drift=drift,
        )
        return {
            "gate": gate.model_dump(mode="json"),
            "protection_drift": drift.model_dump(mode="json"),
            "ready": gate.state is MergeGateState.READY,
        }

    def verify_integrated_tree(self, *, expected_tree: str, observed_tree: str) -> dict[str, Any]:
        matched = expected_tree.lower() == observed_tree.lower()
        return {
            "expected_tree": expected_tree.lower(),
            "observed_tree": observed_tree.lower(),
            "matched": matched,
        }

    def plan_record(
        self,
        *,
        pull_number: int,
        head_sha: str,
        steps: tuple[LifecycleStep, ...],
        jira_reconciled: bool = False,
        integrated_tree_verified: bool = False,
        cleanup_completed: bool = False,
    ) -> LifecycleRecord:
        return LifecycleRecord(
            lifecycle_id=github_identifier(
                "GHLIF", self.repository_slug, str(pull_number), head_sha
            ),
            repository_slug=self.repository_slug,
            pull_number=pull_number,
            head_sha=head_sha.lower(),
            steps=steps,
            jira_reconciled=jira_reconciled,
            integrated_tree_verified=integrated_tree_verified,
            cleanup_completed=cleanup_completed,
        )

    def step_from_operation(self, operation: GitHubOperation) -> LifecycleStep:
        return LifecycleStep(
            step_id=operation.operation_id,
            operation_type=operation.operation_type,
            state=operation.state,
            intent_fingerprint=_fingerprint(
                {
                    "type": operation.operation_type.value,
                    "target": operation.target,
                    "payload": operation.payload,
                }
            ),
            expected_head_sha=operation.expected_head_sha,
            readback=operation.observed_result or {},
            unknown_outcome=operation.state is GitOperationState.UNKNOWN_OUTCOME,
        )

    def _dispatch(self, operation: GitHubOperation, context: GitHubWriteContext) -> dict[str, Any]:
        if operation.operation_type is GitOperationType.MERGE_PULL_REQUEST:
            result = self.remote.merge_pull_request(
                self.repository_slug,
                number=int(operation.target),
                head_sha=str(operation.expected_head_sha),
                method=str(operation.payload.get("method", "squash")),
                context=context,
            )
            readback = self.readback_pull(int(operation.target))
            return {
                "result": dict(result),
                "readback": readback,
                "external_identifier": str(result.get("sha", "")),
            }
        if operation.operation_type is GitOperationType.UPDATE_PULL_REQUEST:
            item = self.remote.update_pull_request(
                self.repository_slug,
                number=int(operation.target),
                fields=operation.payload.get("fields") or {},
                context=context,
            )
            return {
                "readback": item.model_dump(mode="json"),
                "external_identifier": str(item.number),
            }
        if operation.operation_type is GitOperationType.CLOSE_PULL_REQUEST:
            item = self.remote.update_pull_request(
                self.repository_slug,
                number=int(operation.target),
                fields={"state": "CLOSED"},
                context=context,
            )
            return {
                "readback": item.model_dump(mode="json"),
                "external_identifier": str(item.number),
            }
        if operation.operation_type is GitOperationType.DELETE_BRANCH:
            self.remote.delete_branch(
                self.repository_slug,
                branch=str(operation.target),
                context=context,
            )
            remaining = {item.name for item in self.remote.iter_branches(self.repository_slug)}
            return {
                "deleted": operation.target,
                "still_present": operation.target in remaining,
                "external_identifier": operation.target,
            }
        if operation.operation_type is GitOperationType.RECORD_REVIEW:
            receipt = AutonomousReviewReceipt.model_validate(operation.payload["receipt"])
            accepted, blockers = evaluate_autonomous_review(
                receipt, expected_head_sha=str(operation.expected_head_sha)
            )
            if not accepted:
                raise GitHubStewardError(f"autonomous review rejected: {','.join(blockers)}")
            return {"receipt_id": receipt.receipt_id, "accepted": True}
        raise GitHubStewardError(f"unsupported lifecycle operation: {operation.operation_type}")
