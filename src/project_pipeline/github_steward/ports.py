from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from project_pipeline.domain.github import (
    GitBranch,
    GitHubAdapterCapabilities,
    GitHubBranchProtection,
    GitHubReleaseAsset,
    GitHubReleaseSnapshot,
    GitHubRepositoryMetadata,
    PullRequestCheck,
    PullRequestReview,
    PullRequestSnapshot,
)


@dataclass(frozen=True, slots=True)
class GitHubWriteContext:
    actor_id: str
    correlation_id: str
    idempotency_key: str
    authorization_id: str
    expected_head_sha: str | None = None

    def __post_init__(self) -> None:
        for name in ("actor_id", "correlation_id", "idempotency_key", "authorization_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")


@runtime_checkable
class GitHubRemotePort(Protocol):
    provider_id: str

    def discover_capabilities(self) -> GitHubAdapterCapabilities: ...
    def get_repository(self, repository_slug: str) -> GitHubRepositoryMetadata: ...
    def iter_branches(
        self, repository_slug: str, *, page_size: int = 100
    ) -> Iterable[GitBranch]: ...
    def get_branch_protection(
        self, repository_slug: str, branch: str
    ) -> GitHubBranchProtection: ...
    def get_pull_request(self, repository_slug: str, number: int) -> PullRequestSnapshot | None: ...
    def iter_reviews(
        self, repository_slug: str, number: int, *, page_size: int = 100
    ) -> Iterable[PullRequestReview]: ...
    def iter_checks(
        self, repository_slug: str, ref: str, *, page_size: int = 100
    ) -> Iterable[PullRequestCheck]: ...
    def create_branch(
        self, repository_slug: str, *, branch: str, sha: str, context: GitHubWriteContext
    ) -> GitBranch: ...
    def find_open_pull(
        self, repository_slug: str, *, head: str, base: str
    ) -> PullRequestSnapshot | None: ...
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
    ) -> PullRequestSnapshot: ...
    def update_pull_request(
        self,
        repository_slug: str,
        *,
        number: int,
        fields: Mapping[str, Any],
        context: GitHubWriteContext,
    ) -> PullRequestSnapshot: ...
    def merge_pull_request(
        self,
        repository_slug: str,
        *,
        number: int,
        head_sha: str,
        method: str,
        context: GitHubWriteContext,
    ) -> Mapping[str, Any]: ...
    def delete_branch(
        self, repository_slug: str, *, branch: str, context: GitHubWriteContext
    ) -> None: ...
    def list_releases(
        self, repository_slug: str, *, page_size: int = 100
    ) -> Iterable[GitHubReleaseSnapshot]: ...
    def get_release(
        self, repository_slug: str, release_id: int
    ) -> GitHubReleaseSnapshot | None: ...
    def create_draft_release(
        self,
        repository_slug: str,
        *,
        tag_name: str,
        name: str,
        body: str,
        target_commitish: str,
        context: GitHubWriteContext,
    ) -> GitHubReleaseSnapshot: ...
    def upload_release_asset(
        self,
        repository_slug: str,
        *,
        release_id: int,
        name: str,
        content: bytes,
        content_type: str,
        context: GitHubWriteContext,
    ) -> GitHubReleaseAsset: ...
    def download_release_asset(self, repository_slug: str, *, asset_id: int) -> bytes: ...
    def finalize_release(
        self,
        repository_slug: str,
        *,
        release_id: int,
        expected_target_commitish: str,
        context: GitHubWriteContext,
    ) -> GitHubReleaseSnapshot: ...
