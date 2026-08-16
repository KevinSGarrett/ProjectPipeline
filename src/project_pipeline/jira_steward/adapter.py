from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from project_pipeline.contracts import AdapterErrorCategory, AdapterErrorPayload
from project_pipeline.domain.base import utc_now
from project_pipeline.domain.jira import (
    JiraAdapterCapabilities,
    JiraIssueType,
    JiraProjectMetadata,
    RemoteJiraAttachmentReference,
    RemoteJiraComment,
    RemoteJiraIssue,
    RemoteJiraLink,
)
from project_pipeline.jira_steward.ports import JiraRemotePort, JiraWriteContext

_LOCAL_ID_LABEL_PREFIX = "pp-local-id:"
_DEFAULT_FIELDS = (
    "summary",
    "description",
    "status",
    "issuetype",
    "parent",
    "labels",
    "assignee",
    "updated",
    "comment",
    "issuelinks",
    "attachment",
)


class JiraAdapterError(RuntimeError):
    """Typed provider failure. The payload is safe to persist and inspect."""

    def __init__(self, payload: AdapterErrorPayload) -> None:
        super().__init__(payload.message)
        self.payload = payload

    def as_dict(self) -> dict[str, Any]:
        return self.payload.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class JiraHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class AtlassianJiraCloudAdapter(JiraRemotePort):
    """Jira Cloud REST v3 adapter with explicit error and write-safety semantics.

    The adapter performs no implicit retry for mutating requests. Callers must reconcile an
    unknown outcome before retrying with the same idempotency key.
    """

    provider_id = "atlassian-jira-cloud"

    def __init__(
        self,
        *,
        base_url: str,
        user_email: str,
        api_token: str,
        timeout_seconds: float = 30.0,
        maximum_attempts: int = 3,
        retry_base_seconds: float = 0.25,
        local_id_field: str | None = None,
        opener: Any | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        parsed = urllib_parse.urlparse(normalized)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Jira Cloud base_url must be an absolute HTTPS URL")
        if not user_email.strip() or not api_token.strip():
            raise ValueError("Jira Cloud user_email and api_token must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if maximum_attempts < 1 or maximum_attempts > 10:
            raise ValueError("maximum_attempts must be between 1 and 10")
        self.base_url = normalized
        self.user_email = user_email.strip()
        self._api_token = api_token
        self.timeout_seconds = timeout_seconds
        self.maximum_attempts = maximum_attempts
        self.retry_base_seconds = retry_base_seconds
        self.local_id_field = local_id_field
        self._opener = opener or urllib_request.build_opener()

    def discover_capabilities(self) -> JiraAdapterCapabilities:
        self._request_json(
            "GET",
            "/rest/api/3/myself",
            operation="jira.capabilities",
            correlation_id="corr:jira-capabilities",
        )
        return JiraAdapterCapabilities(
            provider="ATLASSIAN_JIRA_CLOUD",
            api_version="3",
            supports_issue_create=True,
            supports_issue_update=True,
            supports_transitions=True,
            supports_comments=True,
            supports_links=True,
            supports_attachments=True,
            supports_webhooks=False,
            pagination_style="NEXT_PAGE_TOKEN",
            maximum_page_size=100,
        )

    def get_project_metadata(self, project_key: str) -> JiraProjectMetadata:
        project = self._request_json(
            "GET",
            f"/rest/api/3/project/{urllib_parse.quote(project_key)}",
            operation="jira.project.read",
            correlation_id=f"corr:jira-project-{project_key.lower()}",
        )
        statuses_payload = self._request_json(
            "GET",
            f"/rest/api/3/project/{urllib_parse.quote(project_key)}/statuses",
            operation="jira.project.statuses.read",
            correlation_id=f"corr:jira-statuses-{project_key.lower()}",
        )
        issue_types = tuple(
            sorted(
                {
                    str(item.get("name", "")).strip()
                    for item in project.get("issueTypes", [])
                    if str(item.get("name", "")).strip()
                }
            )
        )
        status_names: set[str] = set()
        if isinstance(statuses_payload, list):
            for issue_type in statuses_payload:
                for status in (
                    issue_type.get("statuses", []) if isinstance(issue_type, dict) else []
                ):
                    name = str(status.get("name", "")).strip()
                    if name:
                        status_names.add(name)
        components = tuple(
            sorted(
                str(item.get("name", "")).strip()
                for item in project.get("components", [])
                if str(item.get("name", "")).strip()
            )
        )
        return JiraProjectMetadata(
            project_id=str(project.get("id", project_key)),
            project_key=str(project.get("key", project_key)),
            name=str(project.get("name", project_key)),
            issue_types=issue_types,
            statuses=tuple(sorted(status_names)),
            components=components,
            fields={},
        )

    def iter_issues(
        self,
        project_key: str,
        *,
        page_size: int = 100,
        fields: tuple[str, ...] = (),
    ) -> Iterable[RemoteJiraIssue]:
        if page_size < 1 or page_size > 100:
            raise ValueError("Jira Cloud page_size must be between 1 and 100")
        selected_fields = tuple(dict.fromkeys(fields or _DEFAULT_FIELDS))
        next_page_token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": f'project = "{project_key}" ORDER BY key ASC',
                "maxResults": page_size,
                "fields": list(selected_fields),
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            payload = self._request_json(
                "POST",
                "/rest/api/3/search/jql",
                body=body,
                operation="jira.issue.search",
                correlation_id=f"corr:jira-search-{project_key.lower()}",
            )
            issues = payload.get("issues", []) if isinstance(payload, dict) else []
            for item in issues:
                if isinstance(item, dict):
                    yield self._parse_issue(item)
            next_page_token = payload.get("nextPageToken") if isinstance(payload, dict) else None
            if not next_page_token:
                return

    def get_issue(self, remote_key: str) -> RemoteJiraIssue | None:
        try:
            payload = self._request_json(
                "GET",
                f"/rest/api/3/issue/{urllib_parse.quote(remote_key)}?expand=names",
                operation="jira.issue.read",
                correlation_id=f"corr:jira-read-{remote_key.lower()}",
            )
        except JiraAdapterError as exc:
            if exc.payload.category is AdapterErrorCategory.NOT_FOUND:
                return None
            raise
        return self._parse_issue(payload)

    def create_issue(
        self,
        *,
        project_key: str,
        fields: Mapping[str, Any],
        context: JiraWriteContext,
    ) -> RemoteJiraIssue:
        create_fields = self._create_fields(project_key, fields)
        payload = self._request_json(
            "POST",
            "/rest/api/3/issue",
            body={"fields": create_fields},
            operation="jira.issue.create",
            correlation_id=context.correlation_id,
            is_write=True,
            idempotency_key=context.idempotency_key,
        )
        key = str(payload.get("key", "")).strip()
        if not key:
            raise self._error(
                code="JIRA_INVALID_CREATE_RESPONSE",
                category=AdapterErrorCategory.UNKNOWN_OUTCOME,
                message="Jira create response did not contain an issue key; reconciliation is required.",
                retryable=True,
                unknown_outcome=True,
                operation="jira.issue.create",
                correlation_id=context.correlation_id,
                details={"response": payload},
            )
        issue = self.get_issue(key)
        if issue is None:
            raise self._error(
                code="JIRA_CREATED_ISSUE_NOT_OBSERVED",
                category=AdapterErrorCategory.UNKNOWN_OUTCOME,
                message=f"Jira reported created issue {key}, but it could not be read back.",
                retryable=True,
                unknown_outcome=True,
                operation="jira.issue.create",
                correlation_id=context.correlation_id,
                external_operation_id=key,
            )
        return issue

    def update_issue(
        self,
        *,
        remote_key: str,
        fields: Mapping[str, Any],
        context: JiraWriteContext,
    ) -> RemoteJiraIssue:
        update_fields = self._update_fields(fields)
        self._request_json(
            "PUT",
            f"/rest/api/3/issue/{urllib_parse.quote(remote_key)}",
            body={"fields": update_fields},
            operation="jira.issue.update",
            correlation_id=context.correlation_id,
            is_write=True,
            idempotency_key=context.idempotency_key,
        )
        issue = self.get_issue(remote_key)
        if issue is None:
            raise self._error(
                code="JIRA_UPDATED_ISSUE_NOT_OBSERVED",
                category=AdapterErrorCategory.UNKNOWN_OUTCOME,
                message=f"Updated Jira issue {remote_key} could not be read back.",
                retryable=True,
                unknown_outcome=True,
                operation="jira.issue.update",
                correlation_id=context.correlation_id,
                external_operation_id=remote_key,
            )
        return issue

    def transition_issue(
        self,
        *,
        remote_key: str,
        transition_id: str,
        context: JiraWriteContext,
    ) -> RemoteJiraIssue:
        resolved = self._resolve_transition_id(remote_key, transition_id, context.correlation_id)
        self._request_json(
            "POST",
            f"/rest/api/3/issue/{urllib_parse.quote(remote_key)}/transitions",
            body={"transition": {"id": resolved}},
            operation="jira.issue.transition",
            correlation_id=context.correlation_id,
            is_write=True,
            idempotency_key=context.idempotency_key,
        )
        issue = self.get_issue(remote_key)
        if issue is None:
            raise self._error(
                code="JIRA_TRANSITIONED_ISSUE_NOT_OBSERVED",
                category=AdapterErrorCategory.UNKNOWN_OUTCOME,
                message=f"Transitioned Jira issue {remote_key} could not be read back.",
                retryable=True,
                unknown_outcome=True,
                operation="jira.issue.transition",
                correlation_id=context.correlation_id,
                external_operation_id=remote_key,
            )
        return issue

    def add_comment(
        self,
        *,
        remote_key: str,
        body: str,
        context: JiraWriteContext,
    ) -> RemoteJiraComment:
        payload = self._request_json(
            "POST",
            f"/rest/api/3/issue/{urllib_parse.quote(remote_key)}/comment",
            body={"body": self._text_to_adf(body)},
            operation="jira.comment.create",
            correlation_id=context.correlation_id,
            is_write=True,
            idempotency_key=context.idempotency_key,
        )
        return self._parse_comment(payload)

    def create_link(
        self,
        *,
        link_type: str,
        outward_key: str,
        inward_key: str,
        context: JiraWriteContext,
    ) -> RemoteJiraLink:
        self._request_json(
            "POST",
            "/rest/api/3/issueLink",
            body={
                "type": {"name": link_type},
                "outwardIssue": {"key": outward_key},
                "inwardIssue": {"key": inward_key},
            },
            operation="jira.link.create",
            correlation_id=context.correlation_id,
            is_write=True,
            idempotency_key=context.idempotency_key,
        )
        return RemoteJiraLink(
            link_type=link_type,
            outward_key=outward_key,
            inward_key=inward_key,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        operation: str,
        correlation_id: str,
        is_write: bool = False,
        idempotency_key: str | None = None,
    ) -> Any:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization_header(),
            "User-Agent": "Project-Pipeline-Jira-Steward/1.0",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["X-Project-Pipeline-Idempotency-Key"] = idempotency_key
        request = urllib_request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        max_attempts = 1 if is_write else self.maximum_attempts
        for attempt in range(1, max_attempts + 1):
            try:
                response = self._opener.open(request, timeout=self.timeout_seconds)
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
            except urllib_error.HTTPError as exc:
                payload = exc.read()
                adapter_error = self._http_error(
                    exc.code,
                    exc.headers,
                    payload,
                    operation=operation,
                    correlation_id=correlation_id,
                    is_write=is_write,
                )
                if not is_write and adapter_error.payload.retryable and attempt < max_attempts:
                    self._sleep_for_retry(attempt, exc.headers)
                    continue
                raise adapter_error from exc
            except (urllib_error.URLError, TimeoutError, ConnectionError) as exc:
                unknown = is_write
                category = (
                    AdapterErrorCategory.UNKNOWN_OUTCOME
                    if unknown
                    else AdapterErrorCategory.UNAVAILABLE
                )
                adapter_error = self._error(
                    code="JIRA_WRITE_OUTCOME_UNKNOWN" if unknown else "JIRA_UNAVAILABLE",
                    category=category,
                    message=(
                        "Jira write connection failed after dispatch; the remote outcome is unknown."
                        if unknown
                        else "Jira Cloud is unavailable."
                    ),
                    retryable=True,
                    unknown_outcome=unknown,
                    operation=operation,
                    correlation_id=correlation_id,
                    details={"exception_type": type(exc).__name__, "reason": str(exc)},
                )
                if not is_write and attempt < max_attempts:
                    self._sleep_for_retry(attempt, None)
                    continue
                raise adapter_error from exc
            except json.JSONDecodeError as exc:
                raise self._error(
                    code="JIRA_INVALID_JSON_RESPONSE",
                    category=AdapterErrorCategory.TRANSIENT,
                    message="Jira returned an invalid JSON response.",
                    retryable=True,
                    unknown_outcome=is_write,
                    operation=operation,
                    correlation_id=correlation_id,
                    details={"error": str(exc)},
                ) from exc
        raise AssertionError("unreachable Jira HTTP retry state")

    def _http_error(
        self,
        status: int,
        headers: Message | Mapping[str, str] | None,
        body: bytes,
        *,
        operation: str,
        correlation_id: str,
        is_write: bool,
    ) -> JiraAdapterError:
        category, retryable = {
            400: (AdapterErrorCategory.INVALID_REQUEST, False),
            401: (AdapterErrorCategory.AUTHENTICATION, False),
            403: (AdapterErrorCategory.AUTHORIZATION, False),
            404: (AdapterErrorCategory.NOT_FOUND, False),
            409: (AdapterErrorCategory.CONFLICT, False),
            429: (AdapterErrorCategory.RATE_LIMIT, True),
        }.get(
            status,
            (
                AdapterErrorCategory.TRANSIENT if status >= 500 else AdapterErrorCategory.PERMANENT,
                status >= 500,
            ),
        )
        decoded: Any
        try:
            decoded = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = {"body": body[:1000].decode("utf-8", errors="replace")}
        message = self._error_message(decoded) or f"Jira Cloud returned HTTP {status}."
        details: dict[str, Any] = {"http_status": status, "response": decoded}
        retry_after = self._header(headers, "Retry-After")
        if retry_after:
            details["retry_after"] = retry_after
        unknown = bool(is_write and status >= 500)
        if unknown:
            category = AdapterErrorCategory.UNKNOWN_OUTCOME
            retryable = True
        return self._error(
            code="JIRA_WRITE_OUTCOME_UNKNOWN" if unknown else f"JIRA_HTTP_{status}",
            category=category,
            message=message,
            retryable=retryable,
            unknown_outcome=unknown,
            operation=operation,
            correlation_id=correlation_id,
            details=details,
        )

    def _error(
        self,
        *,
        code: str,
        category: AdapterErrorCategory,
        message: str,
        retryable: bool,
        unknown_outcome: bool,
        operation: str,
        correlation_id: str,
        details: Mapping[str, Any] | None = None,
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
                details=dict(details or {}),
            )
        )

    def _authorization_header(self) -> str:
        raw = f"{self.user_email}:{self._api_token}".encode()
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _sleep_for_retry(self, attempt: int, headers: Message | Mapping[str, str] | None) -> None:
        retry_after = self._header(headers, "Retry-After")
        if retry_after:
            try:
                delay = min(float(retry_after), 30.0)
            except ValueError:
                delay = self.retry_base_seconds * (2 ** (attempt - 1))
        else:
            delay = self.retry_base_seconds * (2 ** (attempt - 1))
        time.sleep(max(0.0, delay))

    @staticmethod
    def _header(headers: Message | Mapping[str, str] | None, name: str) -> str | None:
        if headers is None:
            return None
        value = headers.get(name)
        return None if value is None else str(value)

    @staticmethod
    def _error_message(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        messages = payload.get("errorMessages")
        if isinstance(messages, list) and messages:
            return "; ".join(str(item) for item in messages)
        errors = payload.get("errors")
        if isinstance(errors, dict) and errors:
            return "; ".join(f"{key}: {value}" for key, value in sorted(errors.items()))
        return str(payload.get("message", "")).strip()

    def _create_fields(self, project_key: str, source: Mapping[str, Any]) -> dict[str, Any]:
        issue_type = self._remote_issue_type(str(source.get("issue_type", "Task")))
        local_id = str(source.get("local_id", "")).strip()
        labels = list(dict.fromkeys(str(item) for item in source.get("labels", []) if str(item)))
        if local_id:
            marker = f"{_LOCAL_ID_LABEL_PREFIX}{local_id}"
            if marker not in labels:
                labels.append(marker)
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": str(source.get("summary", "")).strip(),
            "issuetype": {"name": issue_type},
            "description": self._text_to_adf(str(source.get("description_text", ""))),
            "labels": labels,
        }
        parent_key = source.get("parent_remote_key")
        if parent_key:
            fields["parent"] = {"key": str(parent_key)}
        if self.local_id_field and local_id:
            fields[self.local_id_field] = local_id
        return fields

    def _update_fields(self, source: Mapping[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if "summary" in source:
            fields["summary"] = source["summary"]
        if "description_text" in source:
            fields["description"] = self._text_to_adf(str(source["description_text"]))
        if "labels" in source:
            fields["labels"] = list(source["labels"])
        if "parent_remote_key" in source:
            fields["parent"] = (
                None
                if source["parent_remote_key"] is None
                else {"key": source["parent_remote_key"]}
            )
        return fields

    @staticmethod
    def _remote_issue_type(value: str) -> str:
        mapping = {
            JiraIssueType.EPIC.value: "Epic",
            JiraIssueType.STORY.value: "Story",
            JiraIssueType.TASK.value: "Task",
            JiraIssueType.SUBTASK.value: "Sub-task",
            JiraIssueType.BUG.value: "Bug",
            JiraIssueType.SPIKE.value: "Spike",
        }
        return mapping.get(value.strip().upper(), value.strip().title() or "Task")

    def _resolve_transition_id(self, remote_key: str, requested: str, correlation_id: str) -> str:
        if requested.isdigit():
            return requested
        payload = self._request_json(
            "GET",
            f"/rest/api/3/issue/{urllib_parse.quote(remote_key)}/transitions",
            operation="jira.issue.transitions.read",
            correlation_id=correlation_id,
        )
        matches = [
            str(item.get("id"))
            for item in payload.get("transitions", [])
            if str(item.get("name", "")).strip().casefold() == requested.strip().casefold()
            or str(item.get("to", {}).get("name", "")).strip().casefold()
            == requested.strip().casefold()
        ]
        if len(matches) != 1:
            raise self._error(
                code="JIRA_TRANSITION_NOT_UNIQUE",
                category=AdapterErrorCategory.CONFLICT,
                message=f"Expected exactly one Jira transition for {requested!r}; observed {len(matches)}.",
                retryable=False,
                unknown_outcome=False,
                operation="jira.issue.transition",
                correlation_id=correlation_id,
                details={"remote_key": remote_key, "requested": requested, "matches": matches},
            )
        return matches[0]

    def _parse_issue(self, payload: Mapping[str, Any]) -> RemoteJiraIssue:
        fields = payload.get("fields", {}) if isinstance(payload.get("fields"), dict) else {}
        labels = tuple(sorted(str(item) for item in fields.get("labels", []) if str(item)))
        local_id = self._local_id(fields, labels)
        issue_type_name = str((fields.get("issuetype") or {}).get("name", "Unknown"))
        normalized_type = self._normalize_issue_type(issue_type_name)
        status_name = str((fields.get("status") or {}).get("name", "Unknown"))
        comments_data = (fields.get("comment") or {}).get("comments", [])
        links_data = fields.get("issuelinks", [])
        attachments_data = fields.get("attachment", [])
        return RemoteJiraIssue(
            remote_id=str(payload.get("id", payload.get("key", "unknown"))),
            remote_key=str(payload.get("key", "")),
            local_id=local_id,
            issue_type_name=issue_type_name,
            normalized_issue_type=normalized_type,
            summary=str(fields.get("summary", "")),
            description_text=self._adf_to_text(fields.get("description")),
            status_name=status_name,
            normalized_state=None,
            parent_remote_key=(
                str((fields.get("parent") or {}).get("key"))
                if (fields.get("parent") or {}).get("key")
                else None
            ),
            labels=labels,
            assignee_account_id=(
                str((fields.get("assignee") or {}).get("accountId"))
                if (fields.get("assignee") or {}).get("accountId")
                else None
            ),
            updated_at_utc=self._parse_datetime(fields.get("updated")),
            version=int(payload["version"]) if payload.get("version") is not None else None,
            comments=tuple(
                self._parse_comment(item) for item in comments_data if isinstance(item, dict)
            ),
            links=tuple(
                self._parse_link(item, str(payload.get("key", "")))
                for item in links_data
                if isinstance(item, dict)
            ),
            attachments=tuple(
                RemoteJiraAttachmentReference(
                    attachment_id=str(item.get("id", "unknown")),
                    filename=str(item.get("filename", "attachment")),
                    media_type=(str(item.get("mimeType")) if item.get("mimeType") else None),
                    size_bytes=int(item.get("size", 0)),
                    content_url=(str(item.get("content")) if item.get("content") else None),
                )
                for item in attachments_data
                if isinstance(item, dict)
            ),
            fields={},
        )

    def _parse_comment(self, payload: Mapping[str, Any]) -> RemoteJiraComment:
        body = self._adf_to_text(payload.get("body"))
        created = self._parse_datetime(payload.get("created"))
        updated = self._parse_datetime(payload.get("updated") or payload.get("created"))
        import hashlib

        fingerprint = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
        return RemoteJiraComment(
            comment_id=str(payload.get("id", "unknown")),
            author_account_id=(
                str((payload.get("author") or {}).get("accountId"))
                if (payload.get("author") or {}).get("accountId")
                else None
            ),
            body_text=body or "(empty comment)",
            created_at_utc=created,
            updated_at_utc=updated,
            semantic_fingerprint=fingerprint,
        )

    @staticmethod
    def _parse_link(payload: Mapping[str, Any], current_key: str) -> RemoteJiraLink:
        outward = payload.get("outwardIssue") or {}
        inward = payload.get("inwardIssue") or {}
        outward_key = str(outward.get("key") or current_key)
        inward_key = str(inward.get("key") or current_key)
        if outward_key == inward_key:
            other = str(outward.get("key") or inward.get("key") or current_key)
            outward_key, inward_key = current_key, other
        return RemoteJiraLink(
            link_id=str(payload.get("id")) if payload.get("id") is not None else None,
            link_type=str((payload.get("type") or {}).get("name", "Relates")),
            outward_key=outward_key,
            inward_key=inward_key,
        )

    def _local_id(self, fields: Mapping[str, Any], labels: tuple[str, ...]) -> str | None:
        if self.local_id_field:
            value = fields.get(self.local_id_field)
            if value:
                return str(value)
        for label in labels:
            if label.casefold().startswith(_LOCAL_ID_LABEL_PREFIX):
                return label[len(_LOCAL_ID_LABEL_PREFIX) :]
        for label in labels:
            candidate = label.upper().replace("_", "-")
            if candidate.startswith("PP-"):
                return candidate
        return None

    @staticmethod
    def _normalize_issue_type(value: str) -> JiraIssueType | None:
        normalized = value.strip().upper().replace(" ", "")
        aliases = {"SUB-TASK": "SUBTASK", "SUBTASK": "SUBTASK", "USERSTORY": "STORY"}
        normalized = aliases.get(normalized, normalized)
        try:
            return JiraIssueType(normalized)
        except ValueError:
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if not value:
            return utc_now()
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return utc_now()
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @classmethod
    def _adf_to_text(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(filter(None, (cls._adf_to_text(item) for item in value)))
        if not isinstance(value, dict):
            return str(value)
        if value.get("type") == "text":
            return str(value.get("text", ""))
        content = value.get("content", [])
        parts = [cls._adf_to_text(item) for item in content if item is not None]
        separator = (
            "\n"
            if value.get("type")
            in {"doc", "paragraph", "heading", "bulletList", "orderedList", "listItem"}
            else ""
        )
        return separator.join(part for part in parts if part).strip()

    @staticmethod
    def _text_to_adf(value: str) -> dict[str, Any]:
        paragraphs = value.splitlines() or [""]
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": ([{"type": "text", "text": line}] if line else []),
                }
                for line in paragraphs
            ],
        }
