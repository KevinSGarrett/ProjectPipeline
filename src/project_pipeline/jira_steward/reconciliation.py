from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_pipeline.domain.jira import (
    JiraAuthorityMode,
    JiraConflictKind,
    JiraLifecycleState,
    JiraMirrorBundle,
    JiraReconciliationPlan,
    JiraRemoteSnapshot,
    JiraStatusMapping,
    JiraSyncConflict,
    JiraSyncOperation,
    JiraSyncOperationType,
    LocalJiraIssue,
    RemoteJiraIssue,
    jira_sync_identifier,
)
from project_pipeline.jira_steward.identity import derive_remote_local_id


@dataclass(frozen=True, slots=True)
class JiraReconciliationPolicy:
    authority_mode: JiraAuthorityMode = JiraAuthorityMode.SOURCE_CONTROLLED_LOCAL
    status_mapping: JiraStatusMapping = field(
        default_factory=lambda: JiraStatusMapping(
            remote_to_internal={
                "Backlog": JiraLifecycleState.BACKLOG,
                "To Do": JiraLifecycleState.BACKLOG,
                "Ready": JiraLifecycleState.READY,
                "In Progress": JiraLifecycleState.IN_PROGRESS,
                "Code Review": JiraLifecycleState.REVIEW,
                "Review": JiraLifecycleState.REVIEW,
                "QA": JiraLifecycleState.VALIDATION,
                "Validation": JiraLifecycleState.VALIDATION,
                "Merge Ready": JiraLifecycleState.MERGE_READY,
                "Blocked": JiraLifecycleState.BLOCKED,
                "Done": JiraLifecycleState.DONE,
                "Complete": JiraLifecycleState.DONE,
                "Cancelled": JiraLifecycleState.CANCELLED,
                "Deferred": JiraLifecycleState.DEFERRED,
            }
        )
    )
    preferred_remote_status: dict[JiraLifecycleState, str] = field(
        default_factory=lambda: {
            JiraLifecycleState.BACKLOG: "To Do",
            JiraLifecycleState.READY: "To Do",
            JiraLifecycleState.IN_PROGRESS: "In Progress",
            JiraLifecycleState.REVIEW: "In Progress",
            JiraLifecycleState.VALIDATION: "In Progress",
            JiraLifecycleState.MERGE_READY: "In Progress",
            JiraLifecycleState.BLOCKED: "In Progress",
            JiraLifecycleState.DONE: "Done",
            JiraLifecycleState.CANCELLED: "To Do",
            JiraLifecycleState.DEFERRED: "To Do",
            JiraLifecycleState.FAILED: "In Progress",
            JiraLifecycleState.DISCOVERED: "To Do",
        }
    )
    import_remote_only_issues: bool = False
    require_completion_evidence_for_remote_done: bool = True


class JiraReconciler:
    """Produce deterministic local-versus-remote plans without performing writes."""

    def __init__(self, policy: JiraReconciliationPolicy | None = None) -> None:
        self.policy = policy or JiraReconciliationPolicy()

    def plan(
        self,
        local: JiraMirrorBundle,
        remote: JiraRemoteSnapshot,
    ) -> JiraReconciliationPlan:
        operations: list[JiraSyncOperation] = []
        conflicts: list[JiraSyncConflict] = []
        local_by_id = {item.local_id: item for item in local.issues}
        local_by_remote_key = {
            item.remote_jira_key: item for item in local.issues if item.remote_jira_key is not None
        }
        remote_by_local: dict[str, RemoteJiraIssue] = {}
        duplicates: dict[str, list[str]] = {}
        for item in remote.issues:
            resolved_local_id = item.local_id
            if resolved_local_id is None:
                derivation = derive_remote_local_id(
                    labels=item.labels,
                    description=item.description_text,
                    fields=item.fields,
                )
                if derivation.fail_closed():
                    conflicts.append(
                        self._conflict(
                            JiraConflictKind.DUPLICATE_REMOTE_MAPPING,
                            local_id=None,
                            remote_key=item.remote_key,
                            fields=("local_id",),
                            description=(
                                f"Remote Jira issue {item.remote_key} has conflicting "
                                f"local IDs: {', '.join(derivation.candidates)}."
                            ),
                            required_resolution=(
                                "Resolve duplicate local-ID labels or description markers "
                                "before writing."
                            ),
                        )
                    )
                    continue
                resolved_local_id = derivation.local_id
            if resolved_local_id is None:
                continue
            if resolved_local_id in remote_by_local:
                duplicates.setdefault(
                    resolved_local_id, [remote_by_local[resolved_local_id].remote_key]
                ).append(item.remote_key)
            else:
                remote_by_local[resolved_local_id] = item
        for local_id, keys in sorted(duplicates.items()):
            conflicts.append(
                self._conflict(
                    JiraConflictKind.DUPLICATE_REMOTE_MAPPING,
                    local_id=local_id,
                    remote_key=None,
                    fields=("local_id",),
                    description=f"Multiple remote Jira issues map to {local_id}: {', '.join(keys)}.",
                    required_resolution="Choose one canonical remote issue and remove duplicate mappings.",
                )
            )
        matched_remote_keys: set[str] = set()
        for local_issue in local.issues:
            remote_issue = remote_by_local.get(local_issue.local_id)
            if remote_issue is None and local_issue.remote_jira_key is not None:
                remote_issue = next(
                    (
                        item
                        for item in remote.issues
                        if item.remote_key == local_issue.remote_jira_key
                    ),
                    None,
                )
            if remote_issue is None:
                operations.append(self._create_remote_operation(local.project_key, local_issue))
                continue
            matched_remote_keys.add(remote_issue.remote_key)
            if local_issue.remote_jira_key is None:
                operations.append(
                    JiraSyncOperation.create(
                        operation_type=JiraSyncOperationType.RECORD_REMOTE_MAPPING,
                        local_id=local_issue.local_id,
                        remote_key=remote_issue.remote_key,
                        payload={
                            "local_id": local_issue.local_id,
                            "remote_key": remote_issue.remote_key,
                            "remote_id": remote_issue.remote_id,
                            "remote_version": remote_issue.version,
                            "remote_fingerprint": remote_issue.semantic_fingerprint(),
                        },
                    )
                )
            self._compare_issue(local_issue, remote_issue, operations, conflicts)
        for remote_issue in remote.issues:
            if remote_issue.remote_key in matched_remote_keys:
                continue
            if remote_issue.local_id and remote_issue.local_id in local_by_id:
                continue
            if remote_issue.remote_key in local_by_remote_key:
                continue
            conflicts.append(
                self._conflict(
                    JiraConflictKind.REMOTE_ONLY_ISSUE,
                    local_id=remote_issue.local_id,
                    remote_key=remote_issue.remote_key,
                    fields=("identity",),
                    description=f"Remote Jira issue {remote_issue.remote_key} has no local mirror record.",
                    required_resolution=(
                        "Review and explicitly import, link, or exclude the remote-only issue; do not silently add it to source control."
                    ),
                )
            )
            if self.policy.import_remote_only_issues:
                operations.append(
                    JiraSyncOperation.create(
                        operation_type=JiraSyncOperationType.IMPORT_REMOTE_ISSUE,
                        local_id=remote_issue.local_id,
                        remote_key=remote_issue.remote_key,
                        payload=remote_issue.model_dump(mode="json"),
                    )
                )
        self._plan_relationship_links(local_by_id, remote, operations)
        operations = sorted(
            operations,
            key=lambda item: self._operation_sort_key(item, local_by_id),
        )
        conflicts = sorted(conflicts, key=lambda item: item.conflict_id)
        identity = jira_sync_identifier(
            "JPLAN",
            local.project_key,
            local.fingerprint,
            remote.snapshot_id,
            remote.fingerprint,
            self.policy.authority_mode.value,
            *[item.operation_id for item in operations],
            *[item.conflict_id for item in conflicts],
        )
        return JiraReconciliationPlan(
            plan_id=identity,
            project_key=local.project_key,
            authority_mode=self.policy.authority_mode,
            local_fingerprint=local.fingerprint,
            remote_snapshot_id=remote.snapshot_id,
            remote_fingerprint=remote.fingerprint,
            operations=tuple(operations),
            conflicts=tuple(conflicts),
        )

    def _create_remote_operation(
        self, project_key: str, issue: LocalJiraIssue
    ) -> JiraSyncOperation:
        payload = {
            "project_key": project_key,
            "local_id": issue.local_id,
            "issue_type": issue.issue_type.value,
            "summary": issue.title,
            "description_text": self._remote_description(issue),
            "parent_local_id": (
                issue.parent if issue.issue_type.value in {"STORY", "SUBTASK"} else None
            ),
            "labels": self._managed_labels(issue),
            "target_state": issue.state.value,
            "traceability_fingerprint": issue.traceability_fingerprint(),
        }
        return JiraSyncOperation.create(
            operation_type=JiraSyncOperationType.CREATE_REMOTE_ISSUE,
            local_id=issue.local_id,
            remote_key=None,
            payload=payload,
        )

    def _plan_relationship_links(
        self,
        local_by_id: dict[str, LocalJiraIssue],
        remote: JiraRemoteSnapshot,
        operations: list[JiraSyncOperation],
    ) -> None:
        remote_key_by_local = {
            issue.local_id: issue.remote_key
            for issue in remote.issues
            if issue.local_id is not None
        }
        observed_links = {
            (link.link_type.casefold(), link.outward_key, link.inward_key)
            for issue in remote.issues
            for link in issue.links
        }
        planned: set[tuple[str, str, str]] = set()

        def add_link(
            *,
            link_type: str,
            outward_local_id: str,
            inward_local_id: str,
            semantic_kind: str,
        ) -> None:
            semantic = (link_type.casefold(), outward_local_id, inward_local_id)
            if semantic in planned:
                return
            planned.add(semantic)
            outward_key = remote_key_by_local.get(outward_local_id)
            inward_key = remote_key_by_local.get(inward_local_id)
            if (
                outward_key is not None
                and inward_key is not None
                and (link_type.casefold(), outward_key, inward_key) in observed_links
            ):
                return
            operations.append(
                JiraSyncOperation.create(
                    operation_type=JiraSyncOperationType.CREATE_REMOTE_LINK,
                    local_id=outward_local_id,
                    remote_key=outward_key,
                    payload={
                        "link_type": link_type,
                        "outward_local_id": outward_local_id,
                        "inward_local_id": inward_local_id,
                        "semantic_kind": semantic_kind,
                    },
                )
            )

        for issue in local_by_id.values():
            if issue.issue_type.value == "TASK" and issue.parent is not None:
                add_link(
                    link_type="Parent Of",
                    outward_local_id=issue.parent,
                    inward_local_id=issue.local_id,
                    semantic_kind="LOCAL_HIERARCHY",
                )
            for dependency in issue.dependencies:
                add_link(
                    link_type="Depends On",
                    outward_local_id=issue.local_id,
                    inward_local_id=dependency,
                    semantic_kind="LOCAL_DEPENDENCY",
                )

    def _compare_issue(
        self,
        local: LocalJiraIssue,
        remote: RemoteJiraIssue,
        operations: list[JiraSyncOperation],
        conflicts: list[JiraSyncConflict],
    ) -> None:
        changed_fields: dict[str, Any] = {}
        if remote.summary != local.title:
            changed_fields["summary"] = local.title
        desired_description = self._remote_description(local)
        if self._normalize_description(remote.description_text) != self._normalize_description(
            desired_description
        ):
            changed_fields["description_text"] = desired_description
        required_labels = self._managed_labels(local)
        if sorted(remote.labels) != required_labels:
            changed_fields["labels"] = required_labels
        if (
            remote.normalized_issue_type is not None
            and remote.normalized_issue_type is not local.issue_type
        ):
            conflicts.append(
                self._conflict(
                    JiraConflictKind.HIERARCHY_MISMATCH,
                    local_id=local.local_id,
                    remote_key=remote.remote_key,
                    fields=("issue_type",),
                    description=(
                        f"Local type {local.issue_type.value} differs from remote type "
                        f"{remote.normalized_issue_type.value}."
                    ),
                    required_resolution="Confirm the intended work type before changing Jira hierarchy.",
                )
            )
        if changed_fields:
            operations.append(
                JiraSyncOperation.create(
                    operation_type=JiraSyncOperationType.UPDATE_REMOTE_FIELDS,
                    local_id=local.local_id,
                    remote_key=remote.remote_key,
                    expected_remote_version=remote.version,
                    payload={
                        "remote_key": remote.remote_key,
                        "fields": changed_fields,
                        "local_fingerprint": local.semantic_fingerprint(),
                    },
                )
            )
        remote_state = remote.normalized_state or self.policy.status_mapping.normalize(
            remote.status_name
        )
        if remote_state is None:
            conflicts.append(
                self._conflict(
                    JiraConflictKind.STATUS_UNMAPPED,
                    local_id=local.local_id,
                    remote_key=remote.remote_key,
                    fields=("status",),
                    description=f"Remote status {remote.status_name!r} has no internal mapping.",
                    required_resolution="Add an explicit status mapping before synchronization.",
                )
            )
            return
        if self.policy.authority_mode is JiraAuthorityMode.SOURCE_CONTROLLED_LOCAL:
            target = self.policy.preferred_remote_status.get(local.state)
            if target is None:
                conflicts.append(
                    self._conflict(
                        JiraConflictKind.STATUS_UNMAPPED,
                        local_id=local.local_id,
                        remote_key=remote.remote_key,
                        fields=("status",),
                        description=f"Internal state {local.state.value} has no preferred remote status.",
                        required_resolution="Define a target remote status or resolve the state manually.",
                    )
                )
            elif target != remote.status_name:
                operations.append(
                    JiraSyncOperation.create(
                        operation_type=JiraSyncOperationType.TRANSITION_REMOTE_ISSUE,
                        local_id=local.local_id,
                        remote_key=remote.remote_key,
                        expected_remote_version=remote.version,
                        payload={
                            "remote_key": remote.remote_key,
                            "from_status": remote.status_name,
                            "target_status": target,
                            "target_internal_state": local.state.value,
                        },
                    )
                )
            return
        if remote_state is local.state:
            return
        evidence_reconciliation_required = (
            self.policy.require_completion_evidence_for_remote_done
            and remote_state is JiraLifecycleState.DONE
            and local.state is not JiraLifecycleState.DONE
        )
        operations.append(
            JiraSyncOperation.create(
                operation_type=JiraSyncOperationType.ACCEPT_REMOTE_FIELDS,
                local_id=local.local_id,
                remote_key=remote.remote_key,
                expected_remote_version=remote.version,
                payload={
                    "local_id": local.local_id,
                    "remote_key": remote.remote_key,
                    "field": "state",
                    "observed_remote_status": remote.status_name,
                    "observed_internal_state": remote_state.value,
                    "current_local_state": local.state.value,
                },
            )
        )
        if evidence_reconciliation_required:
            conflicts.append(
                self._conflict(
                    JiraConflictKind.EVIDENCE_RECONCILIATION_REQUIRED,
                    local_id=local.local_id,
                    remote_key=remote.remote_key,
                    fields=("state", "completion_evidence"),
                    description="Remote Jira reports completion while the local evidence-backed record is not done.",
                    required_resolution="Autonomously reconcile acceptance, tests, independent verification, blockers, integrated-main state, and completion evidence before accepting DONE.",
                )
            )

    @staticmethod
    def _managed_labels(issue: LocalJiraIssue) -> list[str]:
        implementation_label = {
            "IMPLEMENTED": "implementation-implemented",
            "LIVE_VERIFIED": "implementation-live-verified",
            "PARTIALLY_IMPLEMENTED": "implementation-partial",
            "PLANNED_ONLY": "implementation-planned",
        }[issue.implementation_state.value]
        return sorted(
            set(issue.labels)
            | {
                issue.local_id.lower(),
                f"pp-local-id:{issue.local_id}",
                f"risk-{issue.risk_classification.lower()}",
                implementation_label,
            }
        )

    @staticmethod
    def _operation_sort_key(
        operation: JiraSyncOperation, local_by_id: dict[str, LocalJiraIssue]
    ) -> tuple[int, int, str]:
        operation_rank = {
            JiraSyncOperationType.RECORD_REMOTE_MAPPING: 0,
            JiraSyncOperationType.CREATE_REMOTE_ISSUE: 1,
            JiraSyncOperationType.UPDATE_REMOTE_FIELDS: 2,
            JiraSyncOperationType.CREATE_REMOTE_LINK: 3,
            JiraSyncOperationType.TRANSITION_REMOTE_ISSUE: 4,
            JiraSyncOperationType.ADD_REMOTE_COMMENT: 5,
            JiraSyncOperationType.ACCEPT_REMOTE_FIELDS: 6,
            JiraSyncOperationType.IMPORT_REMOTE_ISSUE: 7,
            JiraSyncOperationType.NO_OPERATION: 8,
        }
        depth = 0
        issue = local_by_id.get(operation.local_id or "")
        seen: set[str] = set()
        while issue is not None and issue.parent is not None and issue.local_id not in seen:
            seen.add(issue.local_id)
            depth += 1
            issue = local_by_id.get(issue.parent)
        return operation_rank[operation.operation_type], depth, operation.operation_id

    @staticmethod
    def _remote_description(issue: LocalJiraIssue) -> str:
        def bullets(values: tuple[str, ...]) -> str:
            return "\n".join(f"- {value}" for value in values) if values else "- None."

        def section(title: str, value: str) -> str:
            return f"{title}\n{value.strip() or 'None.'}"

        plans = tuple(
            (
                f"{item.plan_id} / {item.section_id} / {item.line_reference} "
                f"({item.authoritative_path}:{item.start_line}-{item.end_line})"
            )
            for item in issue.plan_references
        )
        criteria = tuple(
            (
                f"{item.criterion_id}: {item.statement}\n"
                f"  Method: {item.verification.method}\n"
                f"  Command: {item.verification.command}\n"
                f"  Path: {item.verification.path}\n"
                f"  Current verification status: {item.verification.status.value}"
            )
            for item in issue.acceptance_criteria
        )
        relationships = tuple(f"{item.type.value}: {item.target}" for item in issue.relationships)
        remote_observation = (
            json.dumps(issue.last_observed_remote_state, sort_keys=True, ensure_ascii=False)
            if issue.last_observed_remote_state is not None
            else "None."
        )
        return "\n\n".join(
            (
                section(
                    "Local Work Item",
                    "\n".join(
                        (
                            f"- Local ID: {issue.local_id}",
                            f"- Local issue type: {issue.issue_type.value}",
                            f"- Parent local ID: {issue.parent or 'None.'}",
                            f"- Local lifecycle state: {issue.state.value}",
                            f"- Implementation state: {issue.implementation_state.value}",
                            f"- Risk classification: {issue.risk_classification}",
                            f"- Required capability: {issue.owner_required_capability}",
                            f"- Confirmed remote key: {issue.remote_jira_key or 'None.'}",
                        )
                    ),
                ),
                section("Objective", issue.objective),
                section("Description", issue.description),
                section("Scope", bullets(issue.scope)),
                section("Rationale", issue.rationale),
                section("Requirements / Traceability", bullets(issue.requirement_ids)),
                section("Plan References", bullets(plans)),
                section("Source References", bullets(issue.source_references)),
                section(
                    "Expected Implementation Artifacts",
                    bullets(issue.expected_implementation_artifacts),
                ),
                section("Expected File Locations", bullets(issue.expected_file_locations)),
                section("Acceptance Criteria", bullets(criteria)),
                section("Definition of Done", bullets(issue.definition_of_done)),
                section("Required Tests", bullets(issue.required_tests)),
                section("Evidence Required", bullets(issue.evidence_required)),
                section("Completion Evidence", bullets(issue.completion_evidence)),
                section("Dependencies", bullets(issue.dependencies)),
                section("Blockers", bullets(issue.blockers)),
                section("Relationships", bullets(relationships)),
                section("Upstream Dependencies", bullets(issue.upstream_dependencies)),
                section("Security Impact", issue.security_impact),
                section("Observability Impact", issue.observability_impact),
                section("Rollback / Recovery", issue.rollback_recovery_consideration),
                section("Exclusions", bullets(issue.exclusions)),
                section("Last Observed Remote State", remote_observation),
                section("Traceability Fingerprint", issue.traceability_fingerprint()),
            )
        )

    @staticmethod
    def _normalize_description(value: str) -> str:
        """Compare Jira's ADF round-trip by semantic text, not layout whitespace."""
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _conflict(
        kind: JiraConflictKind,
        *,
        local_id: str | None,
        remote_key: str | None,
        fields: tuple[str, ...],
        description: str,
        required_resolution: str,
    ) -> JiraSyncConflict:
        identifier = jira_sync_identifier(
            "JCON",
            kind.value,
            local_id or "none",
            remote_key or "none",
            ",".join(fields) or "none",
            description,
        )
        return JiraSyncConflict(
            conflict_id=identifier,
            kind=kind,
            local_id=local_id,
            remote_key=remote_key,
            fields=fields,
            description=description,
            required_resolution=required_resolution,
        )


def load_jira_reconciliation_policy(
    root: Path, *, authority_mode: JiraAuthorityMode | None = None
) -> JiraReconciliationPolicy:
    status_path = root / "config" / "jira" / "status_mapping.json"
    policy_path = root / "config" / "jira" / "sync_policy.json"
    status_document = json.loads(status_path.read_text(encoding="utf-8"))
    policy_document = json.loads(policy_path.read_text(encoding="utf-8"))
    status_mapping = JiraStatusMapping(
        remote_to_internal={
            name: JiraLifecycleState(state)
            for name, state in status_document["remote_to_internal"].items()
        }
    )
    preferred = {
        JiraLifecycleState(state): remote_status
        for state, remote_status in policy_document["preferred_remote_status"].items()
    }
    return JiraReconciliationPolicy(
        authority_mode=authority_mode or JiraAuthorityMode(policy_document["authority_mode"]),
        status_mapping=status_mapping,
        preferred_remote_status=preferred,
        import_remote_only_issues=bool(policy_document["import_remote_only_issues"]),
        require_completion_evidence_for_remote_done=bool(
            policy_document["require_completion_evidence_for_remote_done"]
        ),
    )
