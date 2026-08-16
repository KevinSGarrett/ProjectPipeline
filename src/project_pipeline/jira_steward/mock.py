from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, cast

from project_pipeline.contracts import AdapterErrorCategory, AdapterErrorPayload
from project_pipeline.domain.base import utc_now
from project_pipeline.domain.jira import (
    JiraAdapterCapabilities,
    JiraIssueType,
    JiraLifecycleState,
    JiraProjectMetadata,
    RemoteJiraComment,
    RemoteJiraIssue,
    RemoteJiraLink,
)
from project_pipeline.jira_steward.adapter import JiraAdapterError
from project_pipeline.jira_steward.ports import JiraRemotePort, JiraWriteContext


class MockJiraAdapter(JiraRemotePort):
    """Deterministic in-memory provider used only for contract and fault tests."""

    provider_id = "mock-jira"

    def __init__(
        self,
        *,
        project_key: str = "PP",
        page_size: int = 50,
        seed_issues: Iterable[RemoteJiraIssue] = (),
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self.project_key = project_key
        self.page_size = page_size
        self._issues = {item.remote_key: item for item in seed_issues}
        self._comments: dict[str, list[RemoteJiraComment]] = {
            key: list(issue.comments) for key, issue in self._issues.items()
        }
        self._links: list[RemoteJiraLink] = []
        self._idempotency: dict[str, Any] = {}
        self._failures: dict[str, list[AdapterErrorCategory]] = {}
        self.calls: list[tuple[str, str]] = []
        self.pages_observed = 0
        self._next_issue_number = self._infer_next_number()

    def schedule_failure(self, operation: str, category: AdapterErrorCategory) -> None:
        self._failures.setdefault(operation, []).append(category)

    def discover_capabilities(self) -> JiraAdapterCapabilities:
        self._maybe_fail("capabilities", "corr:mock-capabilities")
        return JiraAdapterCapabilities(
            provider="MOCK_JIRA",
            api_version="mock-1",
            supports_issue_create=True,
            supports_issue_update=True,
            supports_transitions=True,
            supports_comments=True,
            supports_links=True,
            supports_attachments=False,
            supports_webhooks=False,
            pagination_style="MOCK_CURSOR",
            maximum_page_size=self.page_size,
        )

    def get_project_metadata(self, project_key: str) -> JiraProjectMetadata:
        self._maybe_fail("project_metadata", f"corr:mock-project-{project_key.lower()}")
        return JiraProjectMetadata(
            project_id=f"mock-{project_key}",
            project_key=project_key,
            name=f"Mock {project_key}",
            issue_types=tuple(item.value for item in JiraIssueType),
            statuses=tuple(item.value for item in JiraLifecycleState),
        )

    def iter_issues(
        self,
        project_key: str,
        *,
        page_size: int = 100,
        fields: tuple[str, ...] = (),
    ) -> Iterable[RemoteJiraIssue]:
        del fields
        self._maybe_fail("iter_issues", f"corr:mock-search-{project_key.lower()}")
        effective = min(page_size, self.page_size)
        ordered = [self._with_children(self._issues[key]) for key in sorted(self._issues)]
        for start in range(0, len(ordered), effective):
            self.pages_observed += 1
            yield from ordered[start : start + effective]

    def get_issue(self, remote_key: str) -> RemoteJiraIssue | None:
        self.calls.append(("get_issue", remote_key))
        self._maybe_fail("get_issue", f"corr:mock-get-{remote_key.lower()}")
        issue = self._issues.get(remote_key)
        return None if issue is None else self._with_children(issue)

    def create_issue(
        self,
        *,
        project_key: str,
        fields: Mapping[str, Any],
        context: JiraWriteContext,
    ) -> RemoteJiraIssue:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return cast(RemoteJiraIssue, replay)
        key = f"{project_key}-{self._next_issue_number}"
        self._next_issue_number += 1
        local_id = str(fields.get("local_id", "")).strip() or None
        type_name = str(fields.get("issue_type", "TASK"))
        try:
            normalized_type = JiraIssueType(type_name.upper())
        except ValueError:
            normalized_type = None
        labels = tuple(sorted(set(str(item) for item in fields.get("labels", ()))))
        issue = RemoteJiraIssue(
            remote_id=f"mock-{key}",
            remote_key=key,
            local_id=local_id,
            issue_type_name=type_name.title(),
            normalized_issue_type=normalized_type,
            summary=str(fields.get("summary", "Untitled mock issue")),
            description_text=str(fields.get("description_text", "")),
            status_name="BACKLOG",
            normalized_state=JiraLifecycleState.BACKLOG,
            parent_remote_key=(
                str(fields["parent_remote_key"]) if fields.get("parent_remote_key") else None
            ),
            labels=labels,
            updated_at_utc=utc_now(),
            version=1,
        )
        self._issues[key] = issue
        self._comments[key] = []
        self.calls.append(("create_issue", key))
        self._persist_then_maybe_fail("create_issue", context, issue, external_id=key)
        self._idempotency[context.idempotency_key] = issue
        return issue

    def update_issue(
        self,
        *,
        remote_key: str,
        fields: Mapping[str, Any],
        context: JiraWriteContext,
    ) -> RemoteJiraIssue:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return cast(RemoteJiraIssue, replay)
        current = self._required_issue(remote_key)
        if (
            context.expected_remote_version is not None
            and current.version != context.expected_remote_version
        ):
            raise self._error(
                AdapterErrorCategory.CONFLICT,
                "MOCK_VERSION_CONFLICT",
                f"Expected remote version {context.expected_remote_version}; observed {current.version}.",
                context.correlation_id,
                "jira.issue.update",
                retryable=False,
            )
        updated = current.model_copy(
            update={
                "summary": str(fields.get("summary", current.summary)),
                "description_text": str(fields.get("description_text", current.description_text)),
                "labels": tuple(
                    sorted(set(str(item) for item in fields.get("labels", current.labels)))
                ),
                "parent_remote_key": fields.get("parent_remote_key", current.parent_remote_key),
                "updated_at_utc": utc_now(),
                "version": (current.version or 0) + 1,
            }
        )
        self._issues[remote_key] = updated
        self.calls.append(("update_issue", remote_key))
        self._persist_then_maybe_fail("update_issue", context, updated, external_id=remote_key)
        self._idempotency[context.idempotency_key] = updated
        return updated

    def transition_issue(
        self,
        *,
        remote_key: str,
        transition_id: str,
        context: JiraWriteContext,
    ) -> RemoteJiraIssue:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return cast(RemoteJiraIssue, replay)
        current = self._required_issue(remote_key)
        target_name = transition_id.strip().upper().replace(" ", "_")
        try:
            target_state = JiraLifecycleState(target_name)
        except ValueError as exc:
            raise self._error(
                AdapterErrorCategory.INVALID_REQUEST,
                "MOCK_TRANSITION_UNKNOWN",
                f"Unknown mock transition {transition_id!r}.",
                context.correlation_id,
                "jira.issue.transition",
                retryable=False,
            ) from exc
        updated = current.model_copy(
            update={
                "status_name": target_state.value,
                "normalized_state": target_state,
                "updated_at_utc": utc_now(),
                "version": (current.version or 0) + 1,
            }
        )
        self._issues[remote_key] = updated
        self.calls.append(("transition_issue", remote_key))
        self._persist_then_maybe_fail("transition_issue", context, updated, external_id=remote_key)
        self._idempotency[context.idempotency_key] = updated
        return updated

    def add_comment(
        self,
        *,
        remote_key: str,
        body: str,
        context: JiraWriteContext,
    ) -> RemoteJiraComment:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return cast(RemoteJiraComment, replay)
        self._required_issue(remote_key)
        timestamp = utc_now()
        fingerprint = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
        comment = RemoteJiraComment(
            comment_id=f"comment-{len(self._comments[remote_key]) + 1}",
            author_account_id="mock-actor",
            body_text=body,
            created_at_utc=timestamp,
            updated_at_utc=timestamp,
            semantic_fingerprint=fingerprint,
        )
        self._comments[remote_key].append(comment)
        self.calls.append(("add_comment", remote_key))
        self._persist_then_maybe_fail(
            "add_comment", context, comment, external_id=comment.comment_id
        )
        self._idempotency[context.idempotency_key] = comment
        return comment

    def create_link(
        self,
        *,
        link_type: str,
        outward_key: str,
        inward_key: str,
        context: JiraWriteContext,
    ) -> RemoteJiraLink:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return cast(RemoteJiraLink, replay)
        self._required_issue(outward_key)
        self._required_issue(inward_key)
        link = RemoteJiraLink(
            link_id=f"link-{len(self._links) + 1}",
            link_type=link_type,
            outward_key=outward_key,
            inward_key=inward_key,
        )
        self._links.append(link)
        self.calls.append(("create_link", outward_key))
        self._persist_then_maybe_fail("create_link", context, link, external_id=link.link_id)
        self._idempotency[context.idempotency_key] = link
        return link

    def seed_issue(
        self,
        *,
        remote_key: str,
        local_id: str | None,
        summary: str,
        state: JiraLifecycleState = JiraLifecycleState.BACKLOG,
        issue_type: JiraIssueType = JiraIssueType.TASK,
        description_text: str = "",
        labels: tuple[str, ...] = (),
        parent_remote_key: str | None = None,
    ) -> RemoteJiraIssue:
        issue = RemoteJiraIssue(
            remote_id=f"mock-{remote_key}",
            remote_key=remote_key,
            local_id=local_id,
            issue_type_name=issue_type.value.title(),
            normalized_issue_type=issue_type,
            summary=summary,
            description_text=description_text,
            status_name=state.value,
            normalized_state=state,
            parent_remote_key=parent_remote_key,
            labels=tuple(sorted(set(labels))),
            updated_at_utc=utc_now(),
            version=1,
        )
        self._issues[remote_key] = issue
        self._comments[remote_key] = []
        self._next_issue_number = max(self._next_issue_number, self._infer_next_number())
        return issue

    def _with_children(self, issue: RemoteJiraIssue) -> RemoteJiraIssue:
        return issue.model_copy(
            update={
                "comments": tuple(self._comments.get(issue.remote_key, ())),
                "links": tuple(
                    item
                    for item in self._links
                    if issue.remote_key in {item.outward_key, item.inward_key}
                ),
            }
        )

    def _required_issue(self, remote_key: str) -> RemoteJiraIssue:
        issue = self._issues.get(remote_key)
        if issue is None:
            raise self._error(
                AdapterErrorCategory.NOT_FOUND,
                "MOCK_ISSUE_NOT_FOUND",
                f"Mock Jira issue not found: {remote_key}",
                f"corr:mock-not-found-{remote_key.lower()}",
                "jira.issue.read",
                retryable=False,
            )
        return issue

    def _infer_next_number(self) -> int:
        numbers = [
            int(key.rsplit("-", 1)[1])
            for key in self._issues
            if key.startswith(f"{self.project_key}-") and key.rsplit("-", 1)[1].isdigit()
        ]
        return max(numbers, default=0) + 1

    def _replay(self, idempotency_key: str) -> Any | None:
        return self._idempotency.get(idempotency_key)

    def _persist_then_maybe_fail(
        self, operation: str, context: JiraWriteContext, result: Any, *, external_id: str | None
    ) -> None:
        failures = self._failures.get(operation, [])
        if failures and failures[0] is AdapterErrorCategory.UNKNOWN_OUTCOME:
            failures.pop(0)
            self._idempotency[context.idempotency_key] = result
            raise self._error(
                AdapterErrorCategory.UNKNOWN_OUTCOME,
                "MOCK_WRITE_OUTCOME_UNKNOWN",
                "Mock provider persisted the write and then simulated a lost response.",
                context.correlation_id,
                f"jira.{operation}",
                retryable=True,
                unknown_outcome=True,
                external_operation_id=external_id,
            )
        self._maybe_fail(operation, context.correlation_id)

    def _maybe_fail(self, operation: str, correlation_id: str) -> None:
        failures = self._failures.get(operation, [])
        if not failures:
            return
        category = failures.pop(0)
        retryable = category in {
            AdapterErrorCategory.RATE_LIMIT,
            AdapterErrorCategory.TIMEOUT,
            AdapterErrorCategory.TRANSIENT,
            AdapterErrorCategory.UNAVAILABLE,
            AdapterErrorCategory.UNKNOWN_OUTCOME,
        }
        raise self._error(
            category,
            f"MOCK_{category.value}",
            f"Mock Jira scheduled failure for {operation}.",
            correlation_id,
            f"jira.{operation}",
            retryable=retryable,
            unknown_outcome=category is AdapterErrorCategory.UNKNOWN_OUTCOME,
        )

    def _error(
        self,
        category: AdapterErrorCategory,
        code: str,
        message: str,
        correlation_id: str,
        operation: str,
        *,
        retryable: bool,
        unknown_outcome: bool = False,
        external_operation_id: str | None = None,
    ) -> JiraAdapterError:
        return JiraAdapterError(
            AdapterErrorPayload(
                error_code=code,
                category=category,
                message=message,
                retryable=retryable,
                unknown_outcome=unknown_outcome,
                provider=self.provider_id,
                operation=operation,
                correlation_id=correlation_id,
                external_operation_id=external_operation_id,
            )
        )
