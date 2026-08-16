from __future__ import annotations

import io
import json
import unittest
from urllib import error as urllib_error

from project_pipeline.contracts import AdapterErrorCategory
from project_pipeline.jira_steward.adapter import AtlassianJiraCloudAdapter, JiraAdapterError
from project_pipeline.jira_steward.ports import JiraWriteContext


class _Response:
    def __init__(self, payload, status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def read(self):
        if self.payload is None:
            return b""
        return json.dumps(self.payload).encode("utf-8")


class _Opener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _issue(key="PP-1", *, local_id="PP-TASK-000001", status="Backlog"):
    return {
        "id": "10001",
        "key": key,
        "fields": {
            "summary": "Typed Jira issue",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Description"}],
                    }
                ],
            },
            "status": {"name": status},
            "issuetype": {"name": "Task"},
            "labels": [f"pp-local-id:{local_id}", "project-pipeline"],
            "updated": "2026-08-14T12:00:00.000+0000",
            "comment": {"comments": []},
            "issuelinks": [],
            "attachment": [],
        },
    }


class JiraCloudAdapterTests(unittest.TestCase):
    def _adapter(self, opener, **kwargs):
        return AtlassianJiraCloudAdapter(
            base_url="https://example.atlassian.net",
            user_email="user@example.com",
            api_token="secret-token",
            opener=opener,
            retry_base_seconds=0,
            **kwargs,
        )

    def test_search_uses_next_page_token_and_extracts_local_identity(self):
        opener = _Opener(
            [
                _Response({"issues": [_issue("PP-1")], "nextPageToken": "next-1"}),
                _Response({"issues": [_issue("PP-2", local_id="PP-TASK-000002")]}),
            ]
        )
        adapter = self._adapter(opener)
        observed = tuple(adapter.iter_issues("PP", page_size=1))
        self.assertEqual([item.remote_key for item in observed], ["PP-1", "PP-2"])
        self.assertEqual(observed[0].local_id, "PP-TASK-000001")
        first_request = opener.requests[0][0]
        self.assertEqual(first_request.method, "POST")
        self.assertTrue(first_request.headers["Authorization"].startswith("Basic "))
        second_body = json.loads(opener.requests[1][0].data)
        self.assertEqual(second_body["nextPageToken"], "next-1")

    def test_rate_limit_read_is_retried_but_write_is_not_blindly_retried(self):
        http_error = urllib_error.HTTPError(
            "https://example.atlassian.net/rest/api/3/myself",
            429,
            "rate limited",
            {"Retry-After": "0"},
            io.BytesIO(json.dumps({"errorMessages": ["slow down"]}).encode()),
        )
        opener = _Opener([http_error, _Response({"accountId": "abc"})])
        capabilities = self._adapter(opener, maximum_attempts=2).discover_capabilities()
        self.assertEqual(capabilities.provider, "ATLASSIAN_JIRA_CLOUD")
        self.assertEqual(len(opener.requests), 2)

        unavailable = urllib_error.URLError("connection reset")
        write_opener = _Opener([unavailable])
        adapter = self._adapter(write_opener, maximum_attempts=5)
        with self.assertRaises(JiraAdapterError) as raised:
            adapter.create_issue(
                project_key="PP",
                fields={
                    "local_id": "PP-TASK-000001",
                    "issue_type": "TASK",
                    "summary": "Create",
                    "description_text": "Description",
                    "labels": [],
                },
                context=JiraWriteContext(
                    actor_id="actor:test",
                    correlation_id="corr:test",
                    idempotency_key="write-attempt-0001",
                    authorization_id="auth:test",
                ),
            )
        self.assertEqual(raised.exception.payload.category, AdapterErrorCategory.UNKNOWN_OUTCOME)
        self.assertTrue(raised.exception.payload.unknown_outcome)
        self.assertEqual(len(write_opener.requests), 1)

    def test_transition_name_is_resolved_and_result_is_read_back(self):
        opener = _Opener(
            [
                _Response(
                    {
                        "transitions": [
                            {"id": "31", "name": "Start Progress", "to": {"name": "In Progress"}}
                        ]
                    }
                ),
                _Response(None),
                _Response(_issue(status="In Progress")),
            ]
        )
        adapter = self._adapter(opener)
        issue = adapter.transition_issue(
            remote_key="PP-1",
            transition_id="In Progress",
            context=JiraWriteContext(
                actor_id="actor:test",
                correlation_id="corr:test",
                idempotency_key="transition-0001",
                authorization_id="auth:test",
            ),
        )
        transition_body = json.loads(opener.requests[1][0].data)
        self.assertEqual(transition_body, {"transition": {"id": "31"}})
        self.assertEqual(issue.status_name, "In Progress")

    def test_subtask_create_fields_use_jira_cloud_name_and_native_parent(self):
        adapter = self._adapter(_Opener([]))
        fields = adapter._create_fields(
            "PP",
            {
                "local_id": "PP-SUBTASK-000001",
                "issue_type": "SUBTASK",
                "summary": "Create governed subtask",
                "description_text": "Description",
                "labels": [],
                "parent_remote_key": "PP-42",
            },
        )
        self.assertEqual(fields["issuetype"], {"name": "Sub-task"})
        self.assertEqual(fields["parent"], {"key": "PP-42"})

    def test_http_authentication_error_is_non_retryable_and_redacts_credentials(self):
        http_error = urllib_error.HTTPError(
            "https://example.atlassian.net/rest/api/3/myself",
            401,
            "unauthorized",
            {},
            io.BytesIO(json.dumps({"errorMessages": ["Unauthorized"]}).encode()),
        )
        adapter = self._adapter(_Opener([http_error]))
        with self.assertRaises(JiraAdapterError) as raised:
            adapter.discover_capabilities()
        payload = raised.exception.as_dict()
        self.assertEqual(payload["category"], "AUTHENTICATION")
        self.assertFalse(payload["retryable"])
        self.assertNotIn("secret-token", json.dumps(payload))
