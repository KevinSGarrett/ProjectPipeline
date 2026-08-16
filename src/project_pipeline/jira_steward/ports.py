from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from project_pipeline.domain.jira import (
    JiraAdapterCapabilities,
    JiraProjectMetadata,
    RemoteJiraComment,
    RemoteJiraIssue,
    RemoteJiraLink,
)


@dataclass(frozen=True, slots=True)
class JiraWriteContext:
    actor_id: str
    correlation_id: str
    idempotency_key: str
    authorization_id: str
    expected_remote_version: int | None = None
    metadata: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        for name in ("actor_id", "correlation_id", "idempotency_key", "authorization_id"):
            value = getattr(self, name)
            if not value or not value.strip():
                raise ValueError(f"{name} must be non-empty")


@runtime_checkable
class JiraRemotePort(Protocol):
    provider_id: str

    def discover_capabilities(self) -> JiraAdapterCapabilities: ...

    def get_project_metadata(self, project_key: str) -> JiraProjectMetadata: ...

    def iter_issues(
        self,
        project_key: str,
        *,
        page_size: int = 100,
        fields: tuple[str, ...] = (),
    ) -> Iterable[RemoteJiraIssue]: ...

    def get_issue(self, remote_key: str) -> RemoteJiraIssue | None: ...

    def create_issue(
        self,
        *,
        project_key: str,
        fields: Mapping[str, Any],
        context: JiraWriteContext,
    ) -> RemoteJiraIssue: ...

    def update_issue(
        self,
        *,
        remote_key: str,
        fields: Mapping[str, Any],
        context: JiraWriteContext,
    ) -> RemoteJiraIssue: ...

    def transition_issue(
        self,
        *,
        remote_key: str,
        transition_id: str,
        context: JiraWriteContext,
    ) -> RemoteJiraIssue: ...

    def add_comment(
        self,
        *,
        remote_key: str,
        body: str,
        context: JiraWriteContext,
    ) -> RemoteJiraComment: ...

    def create_link(
        self,
        *,
        link_type: str,
        outward_key: str,
        inward_key: str,
        context: JiraWriteContext,
    ) -> RemoteJiraLink: ...
