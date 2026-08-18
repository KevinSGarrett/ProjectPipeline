from __future__ import annotations

from typing import Any

from project_pipeline.contracts import ActionIntent, ApprovalState
from project_pipeline.domain.base import utc_now
from project_pipeline.domain.github import (
    AutonomousReviewReceipt,
    BranchGuardianDecision,
    GitHubOperation,
    GitHubOperationReceipt,
    GitOperationState,
    GitOperationType,
    MergeGateDecision,
    MergeGateState,
    OwnershipKind,
    PullRequestSnapshot,
    ResourceOwnershipClaim,
    github_identifier,
)
from project_pipeline.github_steward.errors import GitHubAdapterError, GitHubStewardError
from project_pipeline.github_steward.local_git import (
    LocalGitRepository,
    evaluate_branch_deletion,
    evaluate_branch_guardian,
)
from project_pipeline.github_steward.merge_gate import evaluate_merge_gate
from project_pipeline.github_steward.ownership import OwnershipRegistry
from project_pipeline.github_steward.persistence import GitHubStewardStore
from project_pipeline.github_steward.ports import GitHubRemotePort, GitHubWriteContext
from project_pipeline.github_steward.protection_drift import evaluate_protection_drift
from project_pipeline.github_steward.worktrunk import WorktrunkAdapter, WorktrunkPlan


class RepositorySteward:
    def __init__(
        self, *, local: LocalGitRepository, remote: GitHubRemotePort, store: GitHubStewardStore
    ) -> None:
        self.local = local
        self.remote = remote
        self.store = store

    def plan_worktrunk(
        self,
        adapter: WorktrunkAdapter,
        branch: str,
        *,
        approved: bool = False,
        base: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.local.snapshot()
        protected = {snapshot.default_branch, "main", "master"}
        if snapshot.current_branch in protected and approved:
            raise GitHubStewardError("worktrunk must not mutate protected main directly")
        plan: WorktrunkPlan = adapter.create_plan(self.local.root, branch, base=base)
        return adapter.execute(plan, approved=approved)

    def inspect_local(self) -> dict[str, Any]:
        snapshot = self.local.snapshot()
        branches = self.local.branches()
        worktrees = self.local.worktrees()
        guardian = evaluate_branch_guardian(snapshot, branches, worktrees)
        return {
            "snapshot": snapshot.model_dump(mode="json"),
            "branches": [item.model_dump(mode="json") for item in branches],
            "worktrees": [item.model_dump(mode="json") for item in worktrees],
            "guardian": guardian.model_dump(mode="json"),
        }

    def branch_guardian(self) -> BranchGuardianDecision:
        return evaluate_branch_guardian(
            self.local.snapshot(), self.local.branches(), self.local.worktrees()
        )

    def claim_resource(
        self, *, resource_kind: OwnershipKind, resource: str, owner_task_id: str, workspace_id: str
    ) -> ResourceOwnershipClaim:
        slug = self.local.repository_slug()
        registry = OwnershipRegistry(self.store.active_ownership(slug))
        claim = registry.acquire(
            repository_slug=slug,
            resource_kind=resource_kind,
            resource=resource,
            owner_task_id=owner_task_id,
            workspace_id=workspace_id,
        )
        self.store.save_ownership(claim)
        return claim

    def pull_snapshot(self, repository_slug: str, number: int) -> PullRequestSnapshot:
        pull = self.remote.get_pull_request(repository_slug, number)
        if pull is None:
            raise GitHubStewardError(f"pull request not found: {repository_slug}#{number}")
        reviews = tuple(self.remote.iter_reviews(repository_slug, number))
        checks = tuple(self.remote.iter_checks(repository_slug, pull.head_sha))
        return pull.model_copy(update={"reviews": reviews, "checks": checks})

    def merge_gate(
        self,
        repository_slug: str,
        number: int,
        *,
        required_checks: tuple[str, ...] | None = None,
        approvals_required: int | None = None,
        expected_head_sha: str | None = None,
        autonomous_review: AutonomousReviewReceipt | None = None,
        expected_tree_sha: str | None = None,
        assert_protection_policy: bool = True,
    ) -> MergeGateDecision:
        pull = self.pull_snapshot(repository_slug, number)
        protection = self.remote.get_branch_protection(repository_slug, pull.base_branch)
        checks = protection.required_status_checks if required_checks is None else required_checks
        approvals = (
            protection.required_approving_review_count
            if approvals_required is None
            else approvals_required
        )
        drift_policy = (
            "autonomous_main"
            if assert_protection_policy
            and (repository_slug, pull.base_branch) == ("KevinSGarrett/ProjectPipeline", "main")
            else "auto"
        )
        drift = evaluate_protection_drift(protection, policy=drift_policy)
        gate = evaluate_merge_gate(
            pull,
            required_checks=checks,
            approvals_required=approvals,
            require_head_sha=expected_head_sha,
            autonomous_review=autonomous_review,
            expected_tree_sha=expected_tree_sha,
            protection_drift=drift,
        )
        self.store.save_gate(gate)
        return gate

    def plan_merge(
        self,
        repository_slug: str,
        number: int,
        *,
        actor_id: str,
        correlation_id: str,
        method: str = "squash",
        expected_head_sha: str | None = None,
        autonomous_review: AutonomousReviewReceipt | None = None,
        expected_tree_sha: str | None = None,
        assert_protection_policy: bool = True,
    ) -> tuple[MergeGateDecision, GitHubOperation]:
        pull = self.pull_snapshot(repository_slug, number)
        required_head = (expected_head_sha or pull.head_sha).lower()
        gate = self.merge_gate(
            repository_slug,
            number,
            expected_head_sha=required_head,
            autonomous_review=autonomous_review,
            expected_tree_sha=expected_tree_sha,
            assert_protection_policy=assert_protection_policy,
        )
        for pending in self.store.pending_operations(repository_slug):
            if (
                pending.operation_type is GitOperationType.MERGE_PULL_REQUEST
                and pending.target == str(number)
                and pending.state is GitOperationState.UNKNOWN_OUTCOME
            ):
                raise GitHubStewardError(
                    "unknown-outcome operations must be reconciled before any retry"
                )
        operation = GitHubOperation.create(
            operation_type=GitOperationType.MERGE_PULL_REQUEST,
            repository_slug=repository_slug,
            target=str(number),
            idempotency_key=f"github-merge:{repository_slug}:{number}:{required_head}",
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload={
                "method": method,
                "pull_number": number,
                "review_id": None if autonomous_review is None else autonomous_review.receipt_id,
            },
            expected_head_sha=required_head,
        )
        self.store.save_operation(operation)
        return gate, operation

    def apply_merge(
        self,
        operation: GitHubOperation,
        gate: MergeGateDecision,
        *,
        action_intent: ActionIntent,
        authorization_id: str,
    ) -> GitHubOperationReceipt:
        stored = self.store.get_operation(operation.operation_id)
        if stored is not None and stored.state is GitOperationState.UNKNOWN_OUTCOME:
            raise GitHubStewardError(
                "unknown-outcome operations must be reconciled before any retry"
            )
        if gate.state is not MergeGateState.READY:
            raise GitHubStewardError("Merge Gate is blocked")
        if operation.operation_type is not GitOperationType.MERGE_PULL_REQUEST:
            raise GitHubStewardError("operation is not a pull-request merge")
        self._validate_intent(
            action_intent, target=operation.repository_slug, operation="github.merge"
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
            result = self.remote.merge_pull_request(
                operation.repository_slug,
                number=int(operation.target),
                head_sha=str(operation.expected_head_sha),
                method=str(operation.payload.get("method", "squash")),
                context=context,
            )
        except GitHubAdapterError as exc:
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
            receipt = GitHubOperationReceipt(
                receipt_id=github_identifier("GHREC", operation.operation_id, state.value),
                operation_id=operation.operation_id,
                state=state,
                provider=self.remote.provider_id,
                external_identifier=exc.payload.external_operation_id,
                observed_result=observed,
                reconciliation_required=state is GitOperationState.UNKNOWN_OUTCOME,
            )
            self.store.save_receipt(receipt)
            return receipt
        applied = pending.model_copy(
            update={
                "state": GitOperationState.APPLIED,
                "observed_result": dict(result),
                "updated_at_utc": utc_now(),
            }
        )
        self.store.save_operation(applied)
        receipt = GitHubOperationReceipt(
            receipt_id=github_identifier(
                "GHREC", operation.operation_id, GitOperationState.APPLIED.value
            ),
            operation_id=operation.operation_id,
            state=GitOperationState.APPLIED,
            provider=self.remote.provider_id,
            external_identifier=str(result.get("sha", "")) or None,
            observed_result=dict(result),
        )
        self.store.save_receipt(receipt)
        return receipt

    def cleanup_plan(self, repository_slug: str) -> dict[str, Any]:
        local = {item.name: item for item in self.local.branches()}
        remote = {item.name: item for item in self.remote.iter_branches(repository_slug)}
        default = self.remote.get_repository(repository_slug).default_branch
        worktree_branches = {item.branch for item in self.local.worktrees() if item.branch}
        candidates: list[dict[str, Any]] = []
        protected: list[dict[str, Any]] = []
        for name in sorted(set(local) | set(remote)):
            if name == default:
                protected.append({"branch": name, "reason": "default_branch"})
                continue
            local_branch = local.get(name)
            if name in worktree_branches:
                protected.append({"branch": name, "reason": "active_worktree"})
                continue
            if local_branch and not local_branch.merged_into_default:
                protected.append({"branch": name, "reason": "not_merged_into_default"})
                continue
            deletion = evaluate_branch_deletion(
                branch=name,
                default_branch=default,
                worktree_branches=worktree_branches,
                dirty=bool(local_branch and local_branch.ahead and not local_branch.upstream),
                merged_into_default=None
                if local_branch is None
                else local_branch.merged_into_default,
                remote_only=name in remote and local_branch is None,
                unpublished=bool(local_branch and local_branch.ahead and not local_branch.upstream),
            )
            if not deletion.safe_for_cleanup:
                protected.append(
                    {
                        "branch": name,
                        "reason": "branch_guardian_blocked",
                        "findings": [item.model_dump(mode="json") for item in deletion.findings],
                    }
                )
                continue
            candidates.append(
                {
                    "branch": name,
                    "delete_local": local_branch is not None,
                    "delete_remote": name in remote,
                }
            )
        return {
            "repository_slug": repository_slug,
            "default_branch": default,
            "candidates": candidates,
            "protected": protected,
        }

    @staticmethod
    def _validate_intent(intent: ActionIntent, *, target: str, operation: str) -> None:
        if intent.approval_state is not ApprovalState.APPROVED:
            raise GitHubStewardError("action intent is not approved")
        if (
            intent.authority != "github.steward"
            or intent.target != target
            or intent.operation != operation
        ):
            raise GitHubStewardError(
                "action intent does not authorize the requested GitHub operation"
            )
