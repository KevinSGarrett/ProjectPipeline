from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from project_pipeline.contracts import ActionIntent, ApprovalState
from project_pipeline.domain.jira import (
    JiraCommentIntent,
    JiraConflictKind,
    JiraMirrorBundle,
    JiraOperationState,
    JiraReconciliationPlan,
    JiraRemoteSnapshot,
    JiraSnapshotSource,
    JiraSyncConflict,
    JiraSyncMode,
    JiraSyncOperation,
    JiraSyncOperationType,
    JiraSyncReceipt,
    RemoteJiraIssue,
    jira_sync_identifier,
)
from project_pipeline.jira_steward.adapter import JiraAdapterError
from project_pipeline.jira_steward.comments import validate_comment_intent
from project_pipeline.jira_steward.persistence import JiraSyncStore
from project_pipeline.jira_steward.ports import JiraRemotePort, JiraWriteContext
from project_pipeline.jira_steward.reconciliation import (
    JiraReconciler,
    JiraReconciliationPolicy,
)
from project_pipeline.jira_steward.repository import JiraMirrorRepository


class JiraStewardError(RuntimeError):
    """Raised when a Jira stewardship action violates authority or safety rules."""


class JiraSteward:
    """Deterministic authority for local Jira validation, diffing, and governed writes."""

    def __init__(
        self,
        *,
        root: Path,
        adapter: JiraRemotePort,
        store: JiraSyncStore,
        policy: JiraReconciliationPolicy,
    ) -> None:
        self.root = root.resolve()
        self.adapter = adapter
        self.store = store
        self.policy = policy
        self.local_repository = JiraMirrorRepository(self.root)
        self.reconciler = JiraReconciler(policy)

    def local_bundle(self) -> JiraMirrorBundle:
        report = self.local_repository.validate()
        if not report.valid:
            raise JiraStewardError("local Jira mirror is invalid: " + "; ".join(report.errors))
        return self.local_repository.bundle()

    def capture_remote_snapshot(self, project_key: str) -> JiraRemoteSnapshot:
        issues = tuple(self.adapter.iter_issues(project_key, page_size=100))
        snapshot = JiraRemoteSnapshot.create(
            project_key=project_key,
            issues=issues,
            source=JiraSnapshotSource.REMOTE_JIRA,
        )
        self.store.put_snapshot(snapshot)
        for issue in snapshot.issues:
            if issue.local_id is not None:
                self.store.put_remote_mapping(
                    local_id=issue.local_id,
                    remote_key=issue.remote_key,
                    provider_id=self.adapter.provider_id,
                    source_operation_id=None,
                    remote_fingerprint=issue.semantic_fingerprint(),
                )
        return snapshot

    def plan(self, project_key: str) -> JiraReconciliationPlan:
        local = self.local_bundle()
        if local.project_key != project_key:
            raise JiraStewardError(
                f"local Jira project key {local.project_key} does not match requested {project_key}"
            )
        remote = self.capture_remote_snapshot(project_key)
        plan = self.reconciler.plan(local, remote)
        self.store.put_plan(plan)
        return plan

    def dry_run(
        self,
        plan: JiraReconciliationPlan,
        *,
        actor_id: str,
        correlation_id: str,
    ) -> JiraSyncReceipt:
        self.store.put_plan(plan)
        receipt = self._receipt(
            plan=plan,
            mode=JiraSyncMode.DRY_RUN,
            result="DRY_RUN",
            actor_id=actor_id,
            correlation_id=correlation_id,
            conflict_ids=tuple(item.conflict_id for item in plan.conflicts),
        )
        self.store.put_receipt(receipt)
        return receipt

    def apply(
        self,
        plan: JiraReconciliationPlan,
        *,
        action_intent: ActionIntent,
        authorization_id: str,
    ) -> JiraSyncReceipt:
        self._validate_action_intent(plan, action_intent)
        self.store.put_plan(plan)
        applied: list[str] = []
        failed: list[str] = []
        unknown: list[str] = []
        conflict_ids = [item.conflict_id for item in plan.conflicts]
        created_remote_keys: dict[str, str] = {}

        for operation in plan.operations:
            current_state = self.store.operation_state(operation.operation_id)
            if current_state in {JiraOperationState.APPLIED, JiraOperationState.RECONCILED}:
                applied.append(operation.operation_id)
                continue
            if current_state is JiraOperationState.UNKNOWN_OUTCOME:
                unknown.append(operation.operation_id)
                break
            if (
                operation.requires_human_approval
                and action_intent.approval_state is not ApprovalState.APPROVED
            ):
                self.store.set_operation_state(operation.operation_id, JiraOperationState.REJECTED)
                failed.append(operation.operation_id)
                break
            self.store.set_operation_state(operation.operation_id, JiraOperationState.PENDING)
            context = JiraWriteContext(
                actor_id=action_intent.actor_id,
                correlation_id=action_intent.correlation_id,
                idempotency_key=operation.idempotency_key,
                authorization_id=authorization_id,
                expected_remote_version=operation.expected_remote_version,
                metadata={"plan_id": plan.plan_id, "operation_id": operation.operation_id},
            )
            try:
                remote = self._apply_operation(operation, context, created_remote_keys)
                external_id = remote.remote_key if isinstance(remote, RemoteJiraIssue) else None
                self.store.set_operation_state(
                    operation.operation_id,
                    JiraOperationState.APPLIED,
                    external_operation_id=external_id,
                )
                if isinstance(remote, RemoteJiraIssue) and operation.local_id:
                    created_remote_keys[operation.local_id] = remote.remote_key
                    self.store.put_remote_mapping(
                        local_id=operation.local_id,
                        remote_key=remote.remote_key,
                        provider_id=self.adapter.provider_id,
                        source_operation_id=operation.operation_id,
                        remote_fingerprint=remote.semantic_fingerprint(),
                    )
                applied.append(operation.operation_id)
            except JiraAdapterError as exc:
                payload = exc.as_dict()
                external_id = exc.payload.external_operation_id
                state = (
                    JiraOperationState.UNKNOWN_OUTCOME
                    if exc.payload.unknown_outcome
                    else JiraOperationState.FAILED
                )
                self.store.set_operation_state(
                    operation.operation_id,
                    state,
                    error=payload,
                    external_operation_id=external_id,
                )
                if state is JiraOperationState.UNKNOWN_OUTCOME:
                    unknown.append(operation.operation_id)
                else:
                    failed.append(operation.operation_id)
                break
            except Exception as exc:
                self.store.set_operation_state(
                    operation.operation_id,
                    JiraOperationState.FAILED,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
                failed.append(operation.operation_id)
                break

        snapshot_after: JiraRemoteSnapshot | None = None
        if not unknown:
            try:
                snapshot_after = self.capture_remote_snapshot(plan.project_key)
            except JiraAdapterError:
                snapshot_after = None

        result: Literal["DRY_RUN", "APPLIED", "PARTIAL", "RECONCILIATION_REQUIRED", "REJECTED"]
        if unknown:
            result = "RECONCILIATION_REQUIRED"
            conflict_ids.append(
                jira_sync_identifier(
                    "JCON",
                    JiraConflictKind.UNKNOWN_WRITE_OUTCOME.value,
                    plan.plan_id,
                    *unknown,
                )
            )
        elif failed and applied:
            result = "PARTIAL"
        elif failed:
            result = "REJECTED"
        else:
            result = "APPLIED"
        receipt = self._receipt(
            plan=plan,
            mode=JiraSyncMode.APPLY,
            result=result,
            actor_id=action_intent.actor_id,
            correlation_id=action_intent.correlation_id,
            applied_operation_ids=tuple(applied),
            failed_operation_ids=tuple(failed),
            unknown_outcome_operation_ids=tuple(unknown),
            conflict_ids=tuple(sorted(set(conflict_ids))),
            remote_snapshot_id_after=(snapshot_after.snapshot_id if snapshot_after else None),
        )
        self.store.put_receipt(receipt)
        return receipt

    def post_comment(
        self,
        intent: JiraCommentIntent,
        *,
        action_intent: ActionIntent,
        authorization_id: str,
    ) -> dict[str, Any]:
        validate_comment_intent(intent)
        self._validate_write_intent(action_intent, target=intent.local_id, operation="jira.comment")
        remote_key = self._remote_key_for_local(intent.local_id)
        context = JiraWriteContext(
            actor_id=action_intent.actor_id,
            correlation_id=action_intent.correlation_id,
            idempotency_key=action_intent.idempotency_key,
            authorization_id=authorization_id,
        )
        comment = self.adapter.add_comment(
            remote_key=remote_key,
            body=intent.body,
            context=context,
        )
        return {
            "schema_version": "1.0.0",
            "comment_intent_id": intent.comment_intent_id,
            "remote_key": remote_key,
            "remote_comment": comment.model_dump(mode="json"),
        }

    def compare_import_bundle(self, imported: JiraMirrorBundle) -> tuple[JiraSyncConflict, ...]:
        local = self.local_bundle()
        conflicts: list[JiraSyncConflict] = []
        local_by_id = {item.local_id: item for item in local.issues}
        imported_by_id = {item.local_id: item for item in imported.issues}
        for local_id in sorted(set(local_by_id) | set(imported_by_id)):
            current = local_by_id.get(local_id)
            candidate = imported_by_id.get(local_id)
            if current is None or candidate is None:
                description = (
                    f"Imported bundle contains local-only difference for {local_id}; "
                    "source-controlled issue records are not modified automatically."
                )
                fields = ("identity",)
            elif current.semantic_fingerprint() == candidate.semantic_fingerprint():
                continue
            else:
                description = (
                    f"Imported bundle and source-controlled mirror diverge for {local_id}."
                )
                fields = ("semantic_payload",)
            conflicts.append(
                JiraSyncConflict(
                    conflict_id=jira_sync_identifier(
                        "JCON", JiraConflictKind.LOCAL_AND_REMOTE_DIVERGED.value, local_id, *fields
                    ),
                    kind=JiraConflictKind.LOCAL_AND_REMOTE_DIVERGED,
                    local_id=local_id,
                    fields=fields,
                    description=description,
                    required_resolution=(
                        "Review the proposed import, update authoritative JSON explicitly, then rebuild and validate Jira indexes."
                    ),
                )
            )
        return tuple(conflicts)

    def status(self, project_key: str | None = None) -> dict[str, Any]:
        local = self.local_repository.validate()
        return {
            "schema_version": "1.0.0",
            "provider": self.adapter.provider_id,
            "authority_mode": self.policy.authority_mode.value,
            "local_mirror": local.as_dict(),
            "sync_store": self.store.status(project_key),
        }

    def _apply_operation(
        self,
        operation: JiraSyncOperation,
        context: JiraWriteContext,
        created_remote_keys: Mapping[str, str],
    ) -> RemoteJiraIssue | None:
        if operation.operation_type is JiraSyncOperationType.CREATE_REMOTE_ISSUE:
            fields = dict(operation.payload)
            parent_local = fields.pop("parent_local_id", None)
            if parent_local:
                parent_remote = created_remote_keys.get(
                    str(parent_local)
                ) or self.store.remote_key_for(str(parent_local))
                if parent_remote is None:
                    parent_issue = self.local_repository.by_id().get(str(parent_local))
                    parent_remote = None if parent_issue is None else parent_issue.remote_jira_key
                if parent_remote is None:
                    raise JiraStewardError(
                        f"cannot create {operation.local_id}; parent {parent_local} has no remote mapping"
                    )
                fields["parent_remote_key"] = parent_remote
            return self.adapter.create_issue(
                project_key=str(fields.pop("project_key")), fields=fields, context=context
            )
        if operation.operation_type is JiraSyncOperationType.UPDATE_REMOTE_FIELDS:
            remote_key = operation.remote_key or str(operation.payload["remote_key"])
            return self.adapter.update_issue(
                remote_key=remote_key,
                fields=dict(operation.payload.get("fields", {})),
                context=context,
            )
        if operation.operation_type is JiraSyncOperationType.TRANSITION_REMOTE_ISSUE:
            remote_key = operation.remote_key or str(operation.payload["remote_key"])
            return self.adapter.transition_issue(
                remote_key=remote_key,
                transition_id=str(operation.payload["target_status"]),
                context=context,
            )
        if operation.operation_type is JiraSyncOperationType.ADD_REMOTE_COMMENT:
            remote_key = operation.remote_key or str(operation.payload["remote_key"])
            self.adapter.add_comment(
                remote_key=remote_key,
                body=str(operation.payload["body"]),
                context=context,
            )
            return self.adapter.get_issue(remote_key)
        if operation.operation_type is JiraSyncOperationType.CREATE_REMOTE_LINK:
            outward_key = operation.payload.get("outward_key")
            if outward_key is None:
                outward_local_id = str(operation.payload["outward_local_id"])
                outward_key = created_remote_keys.get(
                    outward_local_id
                ) or self.store.remote_key_for(outward_local_id)
            inward_key = operation.payload.get("inward_key")
            if inward_key is None:
                inward_local_id = str(operation.payload["inward_local_id"])
                inward_key = created_remote_keys.get(inward_local_id) or self.store.remote_key_for(
                    inward_local_id
                )
            if outward_key is None or inward_key is None:
                raise JiraStewardError(
                    f"cannot create Jira link for {operation.operation_id}; both issues require remote mappings"
                )
            self.adapter.create_link(
                link_type=str(operation.payload["link_type"]),
                outward_key=str(outward_key),
                inward_key=str(inward_key),
                context=context,
            )
            return None
        if operation.operation_type is JiraSyncOperationType.RECORD_REMOTE_MAPPING:
            local_id = operation.local_id or str(operation.payload["local_id"])
            remote_key = operation.remote_key or str(operation.payload["remote_key"])
            self.store.put_remote_mapping(
                local_id=local_id,
                remote_key=remote_key,
                provider_id=self.adapter.provider_id,
                source_operation_id=operation.operation_id,
                remote_fingerprint=None,
            )
            return self.adapter.get_issue(remote_key)
        if operation.operation_type is JiraSyncOperationType.NO_OPERATION:
            return None
        if operation.operation_type in {
            JiraSyncOperationType.IMPORT_REMOTE_ISSUE,
            JiraSyncOperationType.ACCEPT_REMOTE_FIELDS,
        }:
            raise JiraStewardError(
                f"{operation.operation_type.value} requires an explicit source-control change workflow"
            )
        raise JiraStewardError(
            f"unsupported Jira synchronization operation: {operation.operation_type}"
        )

    def _remote_key_for_local(self, local_id: str) -> str:
        mapped = self.store.remote_key_for(local_id)
        if mapped:
            return mapped
        issue = self.local_repository.by_id().get(local_id)
        if issue and issue.remote_jira_key:
            return issue.remote_jira_key
        raise JiraStewardError(f"local Jira issue has no remote mapping: {local_id}")

    def _validate_action_intent(
        self, plan: JiraReconciliationPlan, action_intent: ActionIntent
    ) -> None:
        self._validate_write_intent(action_intent, target=plan.project_key, operation="jira.sync")
        if action_intent.approval_state is not ApprovalState.APPROVED:
            raise JiraStewardError("remote Jira synchronization requires explicit approval")
        if plan.conflicts and "jira:resolve-conflicts" not in action_intent.scope:
            raise JiraStewardError(
                "plan contains reconciliation conflicts; jira:resolve-conflicts scope is required"
            )

    @staticmethod
    def _validate_write_intent(action_intent: ActionIntent, *, target: str, operation: str) -> None:
        if action_intent.authority != "jira.steward":
            raise JiraStewardError("Jira writes require jira.steward authority")
        if action_intent.operation != operation:
            raise JiraStewardError(
                f"action intent operation must be {operation}, observed {action_intent.operation}"
            )
        if action_intent.target != target:
            raise JiraStewardError(
                f"action intent target must be {target}, observed {action_intent.target}"
            )
        if action_intent.approval_state is not ApprovalState.APPROVED:
            raise JiraStewardError("Jira write action intent must be approved")

    @staticmethod
    def _receipt(
        *,
        plan: JiraReconciliationPlan,
        mode: JiraSyncMode,
        result: Literal["DRY_RUN", "APPLIED", "PARTIAL", "RECONCILIATION_REQUIRED", "REJECTED"],
        actor_id: str,
        correlation_id: str,
        applied_operation_ids: tuple[str, ...] = (),
        failed_operation_ids: tuple[str, ...] = (),
        unknown_outcome_operation_ids: tuple[str, ...] = (),
        conflict_ids: tuple[str, ...] = (),
        remote_snapshot_id_after: str | None = None,
    ) -> JiraSyncReceipt:
        receipt_id = jira_sync_identifier(
            "JREC",
            plan.plan_id,
            mode.value,
            result,
            actor_id,
            correlation_id,
            *applied_operation_ids,
            *failed_operation_ids,
            *unknown_outcome_operation_ids,
        )
        return JiraSyncReceipt(
            receipt_id=receipt_id,
            plan_id=plan.plan_id,
            mode=mode,
            result=result,
            applied_operation_ids=applied_operation_ids,
            failed_operation_ids=failed_operation_ids,
            unknown_outcome_operation_ids=unknown_outcome_operation_ids,
            conflict_ids=conflict_ids,
            remote_snapshot_id_after=remote_snapshot_id_after,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
