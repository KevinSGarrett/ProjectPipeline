from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Iterable, Mapping
from typing import Any, cast
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from project_pipeline.contracts import AdapterErrorCategory, AdapterErrorPayload
from project_pipeline.domain.base import utc_now
from project_pipeline.domain.github import (
    BranchRole,
    CheckConclusion,
    CheckState,
    GitBranch,
    GitHubAdapterCapabilities,
    GitHubBranchProtection,
    GitHubReleaseAsset,
    GitHubReleaseSnapshot,
    GitHubRepositoryMetadata,
    PullRequestCheck,
    PullRequestReview,
    PullRequestSnapshot,
    PullRequestState,
    ReviewState,
    github_identifier,
)
from project_pipeline.github_steward.errors import GitHubAdapterError
from project_pipeline.github_steward.ports import GitHubRemotePort, GitHubWriteContext

_API_VERSION = "2026-03-10"


class GitHubRestAdapter(GitHubRemotePort):
    provider_id = "github-rest"

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        upload_base_url: str = "https://uploads.github.com",
        timeout_seconds: float = 20.0,
        maximum_attempts: int = 3,
        retry_base_seconds: float = 0.05,
        opener: Any | None = None,
    ) -> None:
        parsed = urllib_parse.urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("GitHub REST base URL must be HTTPS")
        upload_parsed = urllib_parse.urlparse(upload_base_url)
        if upload_parsed.scheme != "https" or not upload_parsed.netloc:
            raise ValueError("GitHub upload base URL must be HTTPS")
        self.base_url = base_url.rstrip("/")
        self.upload_base_url = upload_base_url.rstrip("/")
        self._token = token
        self.timeout_seconds = timeout_seconds
        self.maximum_attempts = max(1, maximum_attempts)
        self.retry_base_seconds = max(0.0, retry_base_seconds)
        self._opener = opener or urllib_request.build_opener()

    def discard_secret_material(self) -> None:
        """Drop a probe's in-memory bearer token before the adapter is released."""

        self._token = None

    def discover_capabilities(self) -> GitHubAdapterCapabilities:
        return GitHubAdapterCapabilities(provider="GITHUB_REST", api_version=_API_VERSION)

    def get_repository(self, repository_slug: str) -> GitHubRepositoryMetadata:
        payload = self._request_json(
            "GET",
            f"/repos/{self._repo_path(repository_slug)}",
            operation="github.repository.read",
            correlation_id="corr:github-repository-read",
        )
        return GitHubRepositoryMetadata(
            repository_slug=repository_slug,
            repository_id=str(payload.get("id", repository_slug)),
            default_branch=str(payload.get("default_branch", "main")),
            private=bool(payload.get("private", False)),
            archived=bool(payload.get("archived", False)),
            disabled=bool(payload.get("disabled", False)),
            allow_merge_commit=payload.get("allow_merge_commit"),
            allow_squash_merge=payload.get("allow_squash_merge"),
            allow_rebase_merge=payload.get("allow_rebase_merge"),
        )

    def iter_branches(self, repository_slug: str, *, page_size: int = 100) -> Iterable[GitBranch]:
        for item in self._iter_pages(
            f"/repos/{self._repo_path(repository_slug)}/branches",
            page_size=page_size,
            operation="github.branches.read",
        ):
            name = str(item.get("name", ""))
            sha = str((item.get("commit") or {}).get("sha", ""))
            if not name or not sha:
                continue
            yield GitBranch(
                branch_id=github_identifier("GHBR", repository_slug, name, sha),
                name=name,
                sha=sha,
                role=BranchRole.UNKNOWN,
                protected=bool(item.get("protected", False)),
            )

    def get_branch_protection(self, repository_slug: str, branch: str) -> GitHubBranchProtection:
        try:
            payload = self._request_json(
                "GET",
                f"/repos/{self._repo_path(repository_slug)}/branches/{urllib_parse.quote(branch, safe='')}/protection",
                operation="github.branch.protection.read",
                correlation_id="corr:github-branch-protection",
            )
        except GitHubAdapterError as exc:
            if exc.payload.category is AdapterErrorCategory.NOT_FOUND:
                return GitHubBranchProtection(
                    repository_slug=repository_slug, branch=branch, protected=False
                )
            if exc.payload.category is AdapterErrorCategory.AUTHORIZATION:
                payload = self._provisioned_api_json(
                    "GET",
                    f"repos/{self._repo_path(repository_slug)}/branches/{branch}/protection",
                    operation="github.branch.protection.read",
                )
            else:
                raise
        return self._protection_from_payload(repository_slug, branch, payload)

    def get_pull_request(self, repository_slug: str, number: int) -> PullRequestSnapshot | None:
        try:
            payload = self._request_json(
                "GET",
                f"/repos/{self._repo_path(repository_slug)}/pulls/{number}",
                operation="github.pull.read",
                correlation_id=f"corr:github-pr-{number}",
            )
        except GitHubAdapterError as exc:
            if exc.payload.category is AdapterErrorCategory.NOT_FOUND:
                return None
            raise
        return self._parse_pull(repository_slug, payload)

    def iter_reviews(
        self, repository_slug: str, number: int, *, page_size: int = 100
    ) -> Iterable[PullRequestReview]:
        for item in self._iter_pages(
            f"/repos/{self._repo_path(repository_slug)}/pulls/{number}/reviews",
            page_size=page_size,
            operation="github.pull.reviews.read",
        ):
            state_raw = str(item.get("state", "PENDING")).upper()
            state = (
                ReviewState(state_raw)
                if state_raw in ReviewState._value2member_map_
                else ReviewState.PENDING
            )
            commit_sha = item.get("commit_id")
            yield PullRequestReview(
                review_id=str(
                    item.get(
                        "id", github_identifier("GHREV", repository_slug, str(number), str(item))
                    )
                ),
                review_node_id=item.get("node_id"),
                author=str((item.get("user") or {}).get("login", "unknown")),
                state=state,
                commit_sha=str(commit_sha).lower() if commit_sha else None,
                submitted_at_utc=item.get("submitted_at"),
            )

    def iter_checks(
        self, repository_slug: str, ref: str, *, page_size: int = 100
    ) -> Iterable[PullRequestCheck]:
        page = 1
        while True:
            payload = self._request_json(
                "GET",
                f"/repos/{self._repo_path(repository_slug)}/commits/{urllib_parse.quote(ref, safe='')}/check-runs?per_page={page_size}&page={page}",
                operation="github.checks.read",
                correlation_id="corr:github-checks",
            )
            rows = payload.get("check_runs", []) if isinstance(payload, dict) else []
            for item in rows:
                status_raw = str(item.get("status", "unknown")).upper()
                state = (
                    CheckState(status_raw)
                    if status_raw in CheckState._value2member_map_
                    else CheckState.UNKNOWN
                )
                conclusion_raw = str(item.get("conclusion") or "UNKNOWN").upper()
                conclusion = (
                    CheckConclusion(conclusion_raw)
                    if conclusion_raw in CheckConclusion._value2member_map_
                    else CheckConclusion.UNKNOWN
                )
                app = item.get("app") if isinstance(item.get("app"), dict) else {}
                app_id = app.get("id")
                yield PullRequestCheck(
                    check_id=str(
                        item.get("id", github_identifier("GHCHK", repository_slug, ref, str(item)))
                    ),
                    name=str(item.get("name", "unnamed-check")),
                    state=state,
                    conclusion=conclusion if state is CheckState.COMPLETED else None,
                    details_url=item.get("details_url"),
                    app_id=int(app_id) if app_id is not None else None,
                )
            if len(rows) < page_size:
                return
            page += 1

    def create_branch(
        self, repository_slug: str, *, branch: str, sha: str, context: GitHubWriteContext
    ) -> GitBranch:
        payload = self._request_json(
            "POST",
            f"/repos/{self._repo_path(repository_slug)}/git/refs",
            body={"ref": f"refs/heads/{branch}", "sha": sha},
            operation="github.branch.create",
            correlation_id=context.correlation_id,
            is_write=True,
        )
        commit_sha = str((payload.get("object") or {}).get("sha", sha))
        return GitBranch(
            branch_id=github_identifier("GHBR", repository_slug, branch, commit_sha),
            name=branch,
            sha=commit_sha,
            role=BranchRole.FEATURE,
        )

    def find_open_pull(
        self, repository_slug: str, *, head: str, base: str
    ) -> PullRequestSnapshot | None:
        owner = repository_slug.split("/", 1)[0]
        query = urllib_parse.urlencode(
            {"state": "open", "head": f"{owner}:{head}", "base": base, "per_page": "10"}
        )
        rows = self._request_json(
            "GET",
            f"/repos/{self._repo_path(repository_slug)}/pulls?{query}",
            operation="github.pull.find",
            correlation_id="corr:github-pull-find",
        )
        if not isinstance(rows, list) or not rows:
            return None
        return self._parse_pull(repository_slug, rows[0])

    def create_pull_request(
        self,
        repository_slug: str,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool,
        context: GitHubWriteContext,
    ) -> PullRequestSnapshot:
        try:
            payload = self._request_json(
                "POST",
                f"/repos/{self._repo_path(repository_slug)}/pulls",
                body={"head": head, "base": base, "title": title, "body": body, "draft": draft},
                operation="github.pull.create",
                correlation_id=context.correlation_id,
                is_write=True,
            )
            return self._parse_pull(repository_slug, payload)
        except GitHubAdapterError as exc:
            if exc.payload.category is not AdapterErrorCategory.AUTHORIZATION:
                raise
            return self._create_pull_via_provisioned_cli(
                repository_slug,
                head=head,
                base=base,
                title=title,
                body=body,
                draft=draft,
                context=context,
            )

    def _create_pull_via_provisioned_cli(
        self,
        repository_slug: str,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool,
        context: GitHubWriteContext,
    ) -> PullRequestSnapshot:
        del context
        args = [
            "gh",
            "pr",
            "create",
            "--repo",
            repository_slug,
            "--head",
            head,
            "--base",
            base,
            "--title",
            title,
            "--body",
            body,
        ]
        if draft:
            args.append("--draft")
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=60,
        )
        if completed.returncode != 0:
            raise self._error(
                AdapterErrorCategory.AUTHORIZATION,
                "GITHUB_CLI_CREATE_DENIED",
                "provisioned GitHub CLI could not create the pull request",
                "corr:github-pull-create-cli",
                "github.pull.create",
                retryable=False,
            )
        url = (completed.stdout or "").strip().splitlines()[-1] if completed.stdout else ""
        number = int(url.rstrip("/").rsplit("/", 1)[-1])
        pull = self.get_pull_request(repository_slug, number)
        if pull is None:
            raise self._error(
                AdapterErrorCategory.NOT_FOUND,
                "GITHUB_CLI_CREATE_UNREADABLE",
                "created pull request could not be read back",
                "corr:github-pull-create-cli",
                "github.pull.create",
                retryable=False,
            )
        return pull

    def update_pull_request(
        self,
        repository_slug: str,
        *,
        number: int,
        fields: Mapping[str, Any],
        context: GitHubWriteContext,
    ) -> PullRequestSnapshot:
        allowed = {
            key: value for key, value in fields.items() if key in {"title", "body", "state", "base"}
        }
        payload = self._request_json(
            "PATCH",
            f"/repos/{self._repo_path(repository_slug)}/pulls/{number}",
            body=allowed,
            operation="github.pull.update",
            correlation_id=context.correlation_id,
            is_write=True,
        )
        return self._parse_pull(repository_slug, payload)

    def merge_pull_request(
        self,
        repository_slug: str,
        *,
        number: int,
        head_sha: str,
        method: str,
        context: GitHubWriteContext,
    ) -> Mapping[str, Any]:
        if method not in {"merge", "squash", "rebase"}:
            raise ValueError("merge method must be merge, squash, or rebase")
        body = {"sha": head_sha, "merge_method": method}
        try:
            return cast(
                Mapping[str, Any],
                self._request_json(
                    "PUT",
                    f"/repos/{self._repo_path(repository_slug)}/pulls/{number}/merge",
                    body=body,
                    operation="github.pull.merge",
                    correlation_id=context.correlation_id,
                    is_write=True,
                ),
            )
        except GitHubAdapterError as exc:
            if exc.payload.category is not AdapterErrorCategory.AUTHORIZATION:
                raise
            return cast(
                Mapping[str, Any],
                self._provisioned_api_json(
                    "PUT",
                    f"repos/{self._repo_path(repository_slug)}/pulls/{number}/merge",
                    body=body,
                    operation="github.pull.merge",
                ),
            )

    def delete_branch(
        self, repository_slug: str, *, branch: str, context: GitHubWriteContext
    ) -> None:
        try:
            self._request_json(
                "DELETE",
                f"/repos/{self._repo_path(repository_slug)}/git/refs/heads/{urllib_parse.quote(branch, safe='')}",
                operation="github.branch.delete",
                correlation_id=context.correlation_id,
                is_write=True,
                allow_empty=True,
            )
        except GitHubAdapterError as exc:
            if exc.payload.category is not AdapterErrorCategory.AUTHORIZATION:
                raise
            self._provisioned_api_json(
                "DELETE",
                f"repos/{self._repo_path(repository_slug)}/git/refs/heads/{branch}",
                operation="github.branch.delete",
                allow_empty=True,
            )

    def list_releases(
        self, repository_slug: str, *, page_size: int = 100
    ) -> Iterable[GitHubReleaseSnapshot]:
        for item in self._iter_pages(
            f"/repos/{self._repo_path(repository_slug)}/releases",
            page_size=page_size,
            operation="github.releases.read",
        ):
            yield self._parse_release(repository_slug, item)

    def get_release(self, repository_slug: str, release_id: int) -> GitHubReleaseSnapshot | None:
        try:
            payload = self._request_json(
                "GET",
                f"/repos/{self._repo_path(repository_slug)}/releases/{release_id}",
                operation="github.release.read",
                correlation_id=f"corr:github-release-{release_id}",
            )
        except GitHubAdapterError as exc:
            if exc.payload.category is AdapterErrorCategory.NOT_FOUND:
                return None
            raise
        if not isinstance(payload, dict):
            return None
        return self._parse_release(repository_slug, payload)

    def create_draft_release(
        self,
        repository_slug: str,
        *,
        tag_name: str,
        name: str,
        body: str,
        target_commitish: str,
        context: GitHubWriteContext,
    ) -> GitHubReleaseSnapshot:
        payload = self._request_json(
            "POST",
            f"/repos/{self._repo_path(repository_slug)}/releases",
            body={
                "tag_name": tag_name,
                "name": name,
                "body": body,
                "draft": True,
                "prerelease": True,
                "target_commitish": target_commitish,
            },
            operation="github.release.create",
            correlation_id=context.correlation_id,
            is_write=True,
        )
        return self._parse_release(repository_slug, payload)

    def upload_release_asset(
        self,
        repository_slug: str,
        *,
        release_id: int,
        name: str,
        content: bytes,
        content_type: str,
        context: GitHubWriteContext,
    ) -> GitHubReleaseAsset:
        quoted = urllib_parse.quote(name, safe="")
        path = (
            f"/repos/{self._repo_path(repository_slug)}/releases/{release_id}/assets?name={quoted}"
        )
        payload = self._request_raw(
            "POST",
            self.upload_base_url + path,
            data=content,
            extra_headers={"Content-Type": content_type},
            operation="github.release.upload",
            correlation_id=context.correlation_id,
            is_write=True,
        )
        document = json.loads(payload.decode("utf-8")) if payload else {}
        return self._parse_asset(
            repository_slug, document, content_sha256=hashlib.sha256(content).hexdigest()
        )

    def download_release_asset(self, repository_slug: str, *, asset_id: int) -> bytes:
        return self._request_raw(
            "GET",
            f"/repos/{self._repo_path(repository_slug)}/releases/assets/{asset_id}",
            extra_headers={"Accept": "application/octet-stream"},
            operation="github.release.download",
            correlation_id=f"corr:github-asset-{asset_id}",
        )

    def finalize_release(
        self,
        repository_slug: str,
        *,
        release_id: int,
        expected_target_commitish: str,
        context: GitHubWriteContext,
    ) -> GitHubReleaseSnapshot:
        current = self.get_release(repository_slug, release_id)
        if current is None:
            raise self._error(
                AdapterErrorCategory.NOT_FOUND,
                "GITHUB_RELEASE_MISSING",
                "Release is missing",
                context.correlation_id,
                "github.release.finalize",
                retryable=False,
            )
        if current.target_commitish.lower() != expected_target_commitish.lower():
            raise self._error(
                AdapterErrorCategory.CONFLICT,
                "GITHUB_RELEASE_HEAD_CHANGED",
                "Release target changed",
                context.correlation_id,
                "github.release.finalize",
                retryable=False,
            )
        payload = self._request_json(
            "PATCH",
            f"/repos/{self._repo_path(repository_slug)}/releases/{release_id}",
            body={"draft": False},
            operation="github.release.finalize",
            correlation_id=context.correlation_id,
            is_write=True,
        )
        return self._parse_release(repository_slug, payload)

    def _iter_pages(self, path: str, *, page_size: int, operation: str) -> Iterable[dict[str, Any]]:
        if page_size < 1 or page_size > 100:
            raise ValueError("GitHub page_size must be between 1 and 100")
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            payload = self._request_json(
                "GET",
                f"{path}{separator}per_page={page_size}&page={page}",
                operation=operation,
                correlation_id=f"corr:{operation.replace('.', '-')}",
            )
            if not isinstance(payload, list):
                return
            for item in payload:
                if isinstance(item, dict):
                    yield item
            if len(payload) < page_size:
                return
            page += 1

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        operation: str,
        correlation_id: str,
        is_write: bool = False,
        allow_empty: bool = False,
    ) -> Any:
        encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": "Project-Pipeline-Repository-Steward",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        request = urllib_request.Request(
            self.base_url + path, data=encoded, headers=headers, method=method
        )
        attempts = 1 if is_write else self.maximum_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = self._opener.open(request, timeout=self.timeout_seconds)
                raw = response.read()
                if not raw and allow_empty:
                    return {}
                return json.loads(raw.decode("utf-8")) if raw else {}
            except urllib_error.HTTPError as exc:
                payload = self._read_error(exc)
                category, retryable = self._classify_status(exc.code)
                if is_write and category in {
                    AdapterErrorCategory.TIMEOUT,
                    AdapterErrorCategory.TRANSIENT,
                    AdapterErrorCategory.UNAVAILABLE,
                    AdapterErrorCategory.RATE_LIMIT,
                }:
                    category = AdapterErrorCategory.UNKNOWN_OUTCOME
                    retryable = True
                error = self._error(
                    category,
                    f"GITHUB_HTTP_{exc.code}",
                    self._message(payload, exc.reason),
                    correlation_id,
                    operation,
                    retryable=retryable,
                    unknown_outcome=category is AdapterErrorCategory.UNKNOWN_OUTCOME,
                    details={"status": exc.code},
                )
                if not is_write and retryable and attempt < attempts:
                    time.sleep(self.retry_base_seconds * attempt)
                    continue
                raise error from exc
            except (urllib_error.URLError, TimeoutError, ConnectionError) as exc:
                category = (
                    AdapterErrorCategory.UNKNOWN_OUTCOME
                    if is_write
                    else AdapterErrorCategory.UNAVAILABLE
                )
                error = self._error(
                    category,
                    "GITHUB_TRANSPORT_FAILURE",
                    str(getattr(exc, "reason", exc)),
                    correlation_id,
                    operation,
                    retryable=True,
                    unknown_outcome=is_write,
                )
                if not is_write and attempt < attempts:
                    time.sleep(self.retry_base_seconds * attempt)
                    continue
                raise error from exc
        raise AssertionError("unreachable")

    def _request_raw(
        self,
        method: str,
        url_or_path: str,
        *,
        data: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
        operation: str,
        correlation_id: str,
        is_write: bool = False,
    ) -> bytes:
        url = url_or_path if url_or_path.startswith("https://") else self.base_url + url_or_path
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": "Project-Pipeline-Repository-Steward",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if extra_headers:
            headers.update(extra_headers)
        request = urllib_request.Request(url, data=data, headers=headers, method=method)
        attempts = 1 if is_write else self.maximum_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = self._opener.open(request, timeout=self.timeout_seconds)
                return response.read() or b""
            except urllib_error.HTTPError as exc:
                payload = self._read_error(exc)
                category, retryable = self._classify_status(exc.code)
                if is_write and category in {
                    AdapterErrorCategory.TIMEOUT,
                    AdapterErrorCategory.TRANSIENT,
                    AdapterErrorCategory.UNAVAILABLE,
                    AdapterErrorCategory.RATE_LIMIT,
                }:
                    category = AdapterErrorCategory.UNKNOWN_OUTCOME
                    retryable = True
                error = self._error(
                    category,
                    f"GITHUB_HTTP_{exc.code}",
                    self._message(payload, exc.reason),
                    correlation_id,
                    operation,
                    retryable=retryable,
                    unknown_outcome=category is AdapterErrorCategory.UNKNOWN_OUTCOME,
                    details={"status": exc.code},
                )
                if not is_write and retryable and attempt < attempts:
                    time.sleep(self.retry_base_seconds * attempt)
                    continue
                raise error from exc
            except (urllib_error.URLError, TimeoutError, ConnectionError) as exc:
                category = (
                    AdapterErrorCategory.UNKNOWN_OUTCOME
                    if is_write
                    else AdapterErrorCategory.UNAVAILABLE
                )
                error = self._error(
                    category,
                    "GITHUB_TRANSPORT_FAILURE",
                    str(getattr(exc, "reason", exc)),
                    correlation_id,
                    operation,
                    retryable=True,
                    unknown_outcome=is_write,
                )
                if not is_write and attempt < attempts:
                    time.sleep(self.retry_base_seconds * attempt)
                    continue
                raise error from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _read_error(exc: urllib_error.HTTPError) -> Any:
        try:
            raw = exc.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    @staticmethod
    def _message(payload: Any, fallback: Any) -> str:
        if isinstance(payload, dict) and payload.get("message"):
            return str(payload["message"])
        return str(fallback)

    @staticmethod
    def _classify_status(status: int) -> tuple[AdapterErrorCategory, bool]:
        if status == 401:
            return AdapterErrorCategory.AUTHENTICATION, False
        if status == 403:
            return AdapterErrorCategory.AUTHORIZATION, False
        if status == 404:
            return AdapterErrorCategory.NOT_FOUND, False
        if status in {409, 422}:
            return AdapterErrorCategory.CONFLICT, False
        if status == 429:
            return AdapterErrorCategory.RATE_LIMIT, True
        if status >= 500:
            return AdapterErrorCategory.UNAVAILABLE, True
        return AdapterErrorCategory.INVALID_REQUEST, False

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
        details: dict[str, Any] | None = None,
    ) -> GitHubAdapterError:
        return GitHubAdapterError(
            AdapterErrorPayload(
                error_code=code,
                category=category,
                message=message,
                retryable=retryable,
                unknown_outcome=unknown_outcome,
                provider=self.provider_id,
                operation=operation,
                correlation_id=correlation_id,
                details=details or {},
            )
        )

    def _provisioned_api_json(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        body: Any | None = None,
        allow_empty: bool = False,
    ) -> Any:
        args = ["gh", "api", "-X", method, path]
        if body is not None:
            args.extend(["--input", "-"])
        completed = subprocess.run(
            args,
            input=None if body is None else json.dumps(body),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=60,
        )
        if completed.returncode != 0:
            raise self._error(
                AdapterErrorCategory.AUTHORIZATION,
                "GITHUB_CLI_API_DENIED",
                (
                    completed.stderr or completed.stdout or "provisioned GitHub CLI API denied"
                ).strip(),
                f"corr:{operation.replace('.', '-')}",
                operation,
                retryable=False,
            )
        raw = (completed.stdout or "").strip()
        if not raw:
            if allow_empty:
                return {}
            raise self._error(
                AdapterErrorCategory.NOT_FOUND,
                "GITHUB_CLI_API_EMPTY",
                "provisioned GitHub CLI API returned empty output",
                f"corr:{operation.replace('.', '-')}",
                operation,
                retryable=False,
            )
        return json.loads(raw)

    @staticmethod
    def _protection_from_payload(
        repository_slug: str, branch: str, payload: Mapping[str, Any]
    ) -> GitHubBranchProtection:
        status_checks = payload.get("required_status_checks") or {}
        check_bindings = [
            item for item in (status_checks.get("checks") or ()) if isinstance(item, dict)
        ]
        contexts = tuple(
            sorted(str(item) for item in (status_checks.get("contexts") or ()) if str(item).strip())
        )
        if check_bindings:
            names = tuple(str(item.get("context") or "").strip() for item in check_bindings)
            app_ids = tuple(
                int(item["app_id"]) if item.get("app_id") is not None else None
                for item in check_bindings
            )
            contexts_only = False
        else:
            names = contexts
            app_ids = tuple(None for _ in names)
            contexts_only = bool(contexts)
        reviews_raw = payload.get("required_pull_request_reviews")
        reviews = reviews_raw or {}
        return GitHubBranchProtection(
            repository_slug=repository_slug,
            branch=branch,
            protected=True,
            required_status_checks=names,
            required_status_check_app_ids=app_ids,
            contexts_only_required_checks=contexts_only,
            required_status_checks_strict=bool(status_checks.get("strict", False)),
            reviews_object_present=reviews_raw is not None,
            required_approving_review_count=int(
                reviews.get("required_approving_review_count") or 0
            ),
            dismiss_stale_reviews=bool(reviews.get("dismiss_stale_reviews", False)),
            require_code_owner_reviews=bool(reviews.get("require_code_owner_reviews", False)),
            require_last_push_approval=bool(reviews.get("require_last_push_approval", False)),
            enforce_admins=bool((payload.get("enforce_admins") or {}).get("enabled", False)),
            require_linear_history=bool(
                (payload.get("required_linear_history") or {}).get("enabled", False)
            ),
            require_conversation_resolution=bool(
                (payload.get("required_conversation_resolution") or {}).get("enabled", False)
            ),
            allow_force_pushes=bool(
                (payload.get("allow_force_pushes") or {}).get("enabled", False)
            ),
            allow_deletions=bool((payload.get("allow_deletions") or {}).get("enabled", False)),
        )

    @staticmethod
    def _repo_path(slug: str) -> str:
        owner, separator, repo = slug.partition("/")
        if separator != "/" or not owner or not repo or "/" in repo:
            raise ValueError("repository slug must be owner/name")
        return f"{urllib_parse.quote(owner, safe='')}/{urllib_parse.quote(repo, safe='')}"

    @staticmethod
    def _parse_pull(repository_slug: str, payload: Mapping[str, Any]) -> PullRequestSnapshot:
        state_raw = str(payload.get("state", "open")).upper()
        merged = bool(payload.get("merged", False) or payload.get("merged_at"))
        state = (
            PullRequestState.MERGED
            if merged
            else (
                PullRequestState(state_raw)
                if state_raw in PullRequestState._value2member_map_
                else PullRequestState.OPEN
            )
        )
        base = payload.get("base") or {}
        head = payload.get("head") or {}
        number = int(payload.get("number") or 0)
        head_sha = str(head.get("sha", ""))
        return PullRequestSnapshot(
            pull_request_id=github_identifier("GHPR", repository_slug, str(number), head_sha),
            repository_slug=repository_slug,
            number=number,
            title=str(payload.get("title", "Untitled pull request")),
            state=state,
            draft=bool(payload.get("draft", False)),
            base_branch=str(base.get("ref", "")),
            head_branch=str(head.get("ref", "")),
            base_sha=str(base.get("sha", "")),
            head_sha=head_sha,
            mergeable=payload.get("mergeable"),
            mergeable_state=payload.get("mergeable_state"),
            author=str((payload.get("user") or {}).get("login", "")) or None,
            changed_files=int(payload.get("changed_files") or 0),
            additions=int(payload.get("additions") or 0),
            deletions=int(payload.get("deletions") or 0),
            updated_at_utc=payload.get("updated_at") or utc_now(),
        )

    @classmethod
    def _parse_release(
        cls, repository_slug: str, payload: Mapping[str, Any]
    ) -> GitHubReleaseSnapshot:
        api_id = int(payload.get("id") or 0)
        tag_name = str(payload.get("tag_name") or "")
        assets = tuple(
            cls._parse_asset(repository_slug, item)
            for item in (payload.get("assets") or ())
            if isinstance(item, dict)
        )
        return GitHubReleaseSnapshot(
            record_id=github_identifier("GHREL", repository_slug, tag_name, str(api_id)),
            repository_slug=repository_slug,
            api_id=api_id,
            tag_name=tag_name,
            name=str(payload.get("name") or tag_name or "untitled-release"),
            draft=bool(payload.get("draft", True)),
            prerelease=bool(payload.get("prerelease", True)),
            target_commitish=str(payload.get("target_commitish") or ""),
            html_url=str(payload.get("html_url") or "") or None,
            upload_url=str(payload.get("upload_url") or "").split("{", 1)[0] or None,
            body=str(payload.get("body") or ""),
            assets=assets,
        )

    @staticmethod
    def _parse_asset(
        repository_slug: str,
        payload: Mapping[str, Any],
        *,
        content_sha256: str | None = None,
    ) -> GitHubReleaseAsset:
        api_id = int(payload.get("id") or 0)
        name = str(payload.get("name") or "")
        raw = str(payload.get("digest") or payload.get("sha256") or "").replace("sha256:", "")
        digest = content_sha256 or (raw.lower() if len(raw) == 64 else "0" * 64)
        return GitHubReleaseAsset(
            asset_id=github_identifier("GHREL", repository_slug, "asset", name, str(api_id)),
            api_id=api_id,
            name=name,
            sha256=digest,
            size_bytes=int(payload.get("size") or 0),
            content_type=str(payload.get("content_type") or "application/octet-stream"),
            browser_download_url=str(payload.get("browser_download_url") or "") or None,
        )
