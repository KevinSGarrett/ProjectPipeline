from __future__ import annotations

import io
import json
from urllib import error as urllib_error

import pytest

from project_pipeline.contracts import AdapterErrorCategory
from project_pipeline.github_steward.adapter import GitHubRestAdapter
from project_pipeline.github_steward.errors import GitHubAdapterError
from project_pipeline.github_steward.ports import GitHubWriteContext

SHA1 = "a" * 40
SHA2 = "b" * 40


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return b"" if self.payload is None else json.dumps(self.payload).encode()


class Opener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def pull_payload():
    return {
        "number": 4,
        "title": "Feature",
        "state": "open",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "base": {"ref": "main", "sha": SHA1},
        "head": {"ref": "feature/x", "sha": SHA2},
        "user": {"login": "author"},
        "changed_files": 2,
        "additions": 5,
        "deletions": 1,
        "updated_at": "2026-08-14T12:00:00Z",
    }


def test_repository_headers_include_current_version_and_bearer():
    opener = Opener([Response({"id": 1, "default_branch": "main", "private": False})])
    adapter = GitHubRestAdapter(token="secret-token", opener=opener, retry_base_seconds=0)
    repo = adapter.get_repository("owner/repo")
    assert repo.default_branch == "main"
    request = opener.requests[0][0]
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.headers["X-github-api-version"] == "2026-03-10"


def test_pull_reviews_and_checks_are_parsed():
    opener = Opener(
        [
            Response(pull_payload()),
            Response(
                [
                    {
                        "id": 7,
                        "state": "APPROVED",
                        "user": {"login": "reviewer"},
                        "commit_id": SHA2,
                        "submitted_at": "2026-08-14T12:00:00Z",
                    }
                ]
            ),
            Response(
                {
                    "check_runs": [
                        {
                            "id": 8,
                            "name": "tests",
                            "status": "completed",
                            "conclusion": "success",
                            "details_url": "https://example.test",
                        }
                    ]
                }
            ),
        ]
    )
    adapter = GitHubRestAdapter(opener=opener, retry_base_seconds=0)
    pr = adapter.get_pull_request("owner/repo", 4)
    reviews = tuple(adapter.iter_reviews("owner/repo", 4))
    checks = tuple(adapter.iter_checks("owner/repo", SHA2))
    assert pr.number == 4 and pr.head_sha == SHA2
    assert reviews[0].state.value == "APPROVED"
    assert checks[0].conclusion.value == "SUCCESS"


def test_branch_protection_404_is_unprotected():
    err = urllib_error.HTTPError(
        "https://api.github.com",
        404,
        "not found",
        {},
        io.BytesIO(json.dumps({"message": "Not Found"}).encode()),
    )
    adapter = GitHubRestAdapter(opener=Opener([err]), maximum_attempts=1)
    protection = adapter.get_branch_protection("owner/repo", "feature/x")
    assert not protection.protected


def test_read_rate_limit_retries_but_write_transport_failure_is_unknown():
    rate = urllib_error.HTTPError(
        "https://api.github.com",
        429,
        "slow",
        {},
        io.BytesIO(json.dumps({"message": "slow down"}).encode()),
    )
    opener = Opener([rate, Response({"id": 1, "default_branch": "main"})])
    adapter = GitHubRestAdapter(opener=opener, maximum_attempts=2, retry_base_seconds=0)
    assert adapter.get_repository("owner/repo").repository_id == "1"
    assert len(opener.requests) == 2

    write = GitHubRestAdapter(opener=Opener([urllib_error.URLError("reset")]), maximum_attempts=5)
    with pytest.raises(GitHubAdapterError) as raised:
        write.merge_pull_request(
            "owner/repo",
            number=4,
            head_sha=SHA2,
            method="squash",
            context=GitHubWriteContext(
                actor_id="actor:test",
                correlation_id="corr:test",
                idempotency_key="github-merge-0001",
                authorization_id="auth:test",
            ),
        )
    assert raised.value.payload.category is AdapterErrorCategory.UNKNOWN_OUTCOME
    assert raised.value.payload.unknown_outcome


def test_merge_sends_head_sha_and_method():
    opener = Opener([Response({"merged": True, "sha": SHA2, "message": "ok"})])
    adapter = GitHubRestAdapter(opener=opener)
    result = adapter.merge_pull_request(
        "owner/repo",
        number=4,
        head_sha=SHA2,
        method="rebase",
        context=GitHubWriteContext(
            actor_id="actor:test",
            correlation_id="corr:test",
            idempotency_key="github-merge-0002",
            authorization_id="auth:test",
        ),
    )
    body = json.loads(opener.requests[0][0].data)
    assert body == {"sha": SHA2, "merge_method": "rebase"}
    assert result["merged"] is True


def test_delete_branch_uses_git_refs_endpoint():
    opener = Opener([Response(None)])
    adapter = GitHubRestAdapter(opener=opener)
    adapter.delete_branch(
        "owner/repo",
        branch="feature/x",
        context=GitHubWriteContext(
            actor_id="actor:test",
            correlation_id="corr:test",
            idempotency_key="github-delete-0001",
            authorization_id="auth:test",
        ),
    )
    request = opener.requests[0][0]
    assert request.method == "DELETE"
    assert request.full_url.endswith("/repos/owner/repo/git/refs/heads/feature%2Fx")
