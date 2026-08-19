from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from project_pipeline.contracts import AdapterErrorCategory, AdapterErrorPayload
from project_pipeline.domain.base import utc_now
from project_pipeline.domain.github import (
    BranchRole,
    GitBranch,
    GitHubAdapterCapabilities,
    GitHubBranchProtection,
    GitHubRepositoryMetadata,
    PullRequestCheck,
    PullRequestReview,
    PullRequestSnapshot,
    PullRequestState,
    github_identifier,
)
from project_pipeline.github_steward.errors import GitHubAdapterError
from project_pipeline.github_steward.ports import GitHubRemotePort, GitHubWriteContext


class MockGitHubAdapter(GitHubRemotePort):
    provider_id = "mock-github"

    def __init__(
        self,
        *,
        repository_slug: str = "example/project",
        default_branch: str = "main",
        branches: Iterable[GitBranch] = (),
        pulls: Iterable[PullRequestSnapshot] = (),
    ) -> None:
        self.repository_slug = repository_slug
        self.default_branch = default_branch
        self._branches = {item.name: item for item in branches}
        self._pulls = {item.number: item for item in pulls}
        self._reviews: dict[int, list[PullRequestReview]] = {
            item.number: list(item.reviews) for item in pulls
        }
        self._checks: dict[str, list[PullRequestCheck]] = {
            item.head_sha: list(item.checks) for item in pulls
        }
        self._protection = GitHubBranchProtection(
            repository_slug=repository_slug, branch=default_branch, protected=True
        )
        self._idempotency: dict[str, Any] = {}
        self._failures: dict[str, list[AdapterErrorCategory]] = {}
        self.calls: list[tuple[str, str]] = []
        self.pages_observed = 0
        self._next_pull = max(self._pulls, default=0) + 1

    def schedule_failure(self, operation: str, category: AdapterErrorCategory) -> None:
        self._failures.setdefault(operation, []).append(category)

    def set_branch_protection(self, protection: GitHubBranchProtection) -> None:
        self._protection = protection

    def discover_capabilities(self) -> GitHubAdapterCapabilities:
        self._maybe_fail("capabilities", "corr:mock-github-capabilities")
        return GitHubAdapterCapabilities(provider="MOCK_GITHUB", api_version="mock-1")

    def get_repository(self, repository_slug: str) -> GitHubRepositoryMetadata:
        self._maybe_fail("repository", "corr:mock-github-repository")
        return GitHubRepositoryMetadata(
            repository_slug=repository_slug,
            repository_id=f"mock:{repository_slug}",
            default_branch=self.default_branch,
        )

    def iter_branches(self, repository_slug: str, *, page_size: int = 100) -> Iterable[GitBranch]:
        self._maybe_fail("branches", "corr:mock-github-branches")
        ordered = [self._branches[key] for key in sorted(self._branches)]
        for start in range(0, len(ordered), max(1, page_size)):
            self.pages_observed += 1
            yield from ordered[start : start + page_size]

    def get_branch_protection(self, repository_slug: str, branch: str) -> GitHubBranchProtection:
        self._maybe_fail("protection", "corr:mock-github-protection")
        if branch == self._protection.branch:
            return self._protection
        return GitHubBranchProtection(
            repository_slug=repository_slug, branch=branch, protected=False
        )

    def get_pull_request(self, repository_slug: str, number: int) -> PullRequestSnapshot | None:
        self._maybe_fail("pull", f"corr:mock-github-pr-{number}")
        item = self._pulls.get(number)
        if item is None:
            return None
        return item.model_copy(
            update={
                "reviews": tuple(self._reviews.get(number, ())),
                "checks": tuple(self._checks.get(item.head_sha, ())),
            }
        )

    def iter_reviews(
        self, repository_slug: str, number: int, *, page_size: int = 100
    ) -> Iterable[PullRequestReview]:
        self._maybe_fail("reviews", "corr:mock-github-reviews")
        rows = self._reviews.get(number, [])
        for start in range(0, len(rows), max(1, page_size)):
            self.pages_observed += 1
            yield from rows[start : start + page_size]

    def iter_checks(
        self, repository_slug: str, ref: str, *, page_size: int = 100
    ) -> Iterable[PullRequestCheck]:
        self._maybe_fail("checks", "corr:mock-github-checks")
        rows = self._checks.get(ref, [])
        for start in range(0, len(rows), max(1, page_size)):
            self.pages_observed += 1
            yield from rows[start : start + page_size]

    def create_branch(
        self, repository_slug: str, *, branch: str, sha: str, context: GitHubWriteContext
    ) -> GitBranch:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return replay
        if branch in self._branches:
            raise self._error(
                AdapterErrorCategory.CONFLICT,
                "MOCK_BRANCH_EXISTS",
                "Branch already exists",
                context.correlation_id,
                "github.branch.create",
                retryable=False,
            )
        item = GitBranch(
            branch_id=github_identifier("GHBR", repository_slug, branch, sha),
            name=branch,
            sha=sha,
            role=BranchRole.FEATURE,
        )
        self._branches[branch] = item
        self.calls.append(("create_branch", branch))
        self._persist_then_fail("create_branch", context, item, branch)
        self._idempotency[context.idempotency_key] = item
        return item

    def find_open_pull(
        self, repository_slug: str, *, head: str, base: str
    ) -> PullRequestSnapshot | None:
        del repository_slug
        for item in self._pulls.values():
            if (
                item.head_branch == head
                and item.base_branch == base
                and item.state is PullRequestState.OPEN
            ):
                return item
        return None

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
        del body
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return replay
        if head not in self._branches or base not in self._branches:
            raise self._error(
                AdapterErrorCategory.NOT_FOUND,
                "MOCK_BRANCH_MISSING",
                "Head or base branch is missing",
                context.correlation_id,
                "github.pull.create",
                retryable=False,
            )
        number = self._next_pull
        self._next_pull += 1
        item = PullRequestSnapshot(
            pull_request_id=github_identifier(
                "GHPR", repository_slug, str(number), self._branches[head].sha
            ),
            repository_slug=repository_slug,
            number=number,
            title=title,
            state=PullRequestState.OPEN,
            draft=draft,
            base_branch=base,
            head_branch=head,
            base_sha=self._branches[base].sha,
            head_sha=self._branches[head].sha,
            mergeable=True,
            author="mock-actor",
        )
        self._pulls[number] = item
        self._reviews[number] = []
        self._checks[item.head_sha] = []
        self.calls.append(("create_pull_request", str(number)))
        self._persist_then_fail("create_pull_request", context, item, str(number))
        self._idempotency[context.idempotency_key] = item
        return item

    def update_pull_request(
        self,
        repository_slug: str,
        *,
        number: int,
        fields: Mapping[str, Any],
        context: GitHubWriteContext,
    ) -> PullRequestSnapshot:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return replay
        current = self._required_pull(number)
        update: dict[str, Any] = {key: value for key, value in fields.items() if key in {"title"}}
        if "state" in fields:
            update["state"] = PullRequestState(str(fields["state"]).upper())
        item = current.model_copy(update=update | {"updated_at_utc": utc_now()})
        self._pulls[number] = item
        self._persist_then_fail("update_pull_request", context, item, str(number))
        self._idempotency[context.idempotency_key] = item
        return item

    def merge_pull_request(
        self,
        repository_slug: str,
        *,
        number: int,
        head_sha: str,
        method: str,
        context: GitHubWriteContext,
    ) -> Mapping[str, Any]:
        del method
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return replay
        current = self._required_pull(number)
        if current.head_sha != head_sha.lower():
            raise self._error(
                AdapterErrorCategory.CONFLICT,
                "MOCK_HEAD_CHANGED",
                "Pull request head changed",
                context.correlation_id,
                "github.pull.merge",
                retryable=False,
            )
        merged = current.model_copy(
            update={"state": PullRequestState.MERGED, "updated_at_utc": utc_now()}
        )
        self._pulls[number] = merged
        result = {"merged": True, "sha": head_sha, "message": "mock merge applied"}
        self.calls.append(("merge_pull_request", str(number)))
        self._persist_then_fail("merge_pull_request", context, result, str(number))
        self._idempotency[context.idempotency_key] = result
        return result

    def delete_branch(
        self, repository_slug: str, *, branch: str, context: GitHubWriteContext
    ) -> None:
        replay = self._replay(context.idempotency_key)
        if replay is not None:
            return None
        if branch == self.default_branch:
            raise self._error(
                AdapterErrorCategory.INVALID_REQUEST,
                "MOCK_DEFAULT_DELETE",
                "Default branch cannot be deleted",
                context.correlation_id,
                "github.branch.delete",
                retryable=False,
            )
        self._branches.pop(branch, None)
        self.calls.append(("delete_branch", branch))
        self._persist_then_fail("delete_branch", context, {"deleted": branch}, branch)
        self._idempotency[context.idempotency_key] = {"deleted": branch}

    def seed_review(self, number: int, review: PullRequestReview) -> None:
        self._reviews.setdefault(number, []).append(review)

    def seed_check(self, ref: str, check: PullRequestCheck) -> None:
        self._checks.setdefault(ref, []).append(check)

    def _required_pull(self, number: int) -> PullRequestSnapshot:
        item = self._pulls.get(number)
        if item is None:
            raise self._error(
                AdapterErrorCategory.NOT_FOUND,
                "MOCK_PULL_NOT_FOUND",
                f"Pull request {number} not found",
                "corr:mock-github",
                "github.pull.read",
                retryable=False,
            )
        return item

    def _replay(self, key: str) -> Any | None:
        return self._idempotency.get(key)

    def _maybe_fail(self, operation: str, correlation_id: str) -> None:
        failures = self._failures.get(operation, [])
        if failures:
            category = failures.pop(0)
            raise self._error(
                category,
                "MOCK_GITHUB_FAILURE",
                f"Scheduled mock failure: {category.value}",
                correlation_id,
                f"github.{operation}",
                retryable=category
                in {
                    AdapterErrorCategory.RATE_LIMIT,
                    AdapterErrorCategory.TIMEOUT,
                    AdapterErrorCategory.TRANSIENT,
                    AdapterErrorCategory.UNAVAILABLE,
                    AdapterErrorCategory.UNKNOWN_OUTCOME,
                },
            )

    def _persist_then_fail(
        self, operation: str, context: GitHubWriteContext, value: Any, external_id: str
    ) -> None:
        failures = self._failures.get(operation, [])
        if failures:
            category = failures.pop(0)
            if category is AdapterErrorCategory.UNKNOWN_OUTCOME:
                raise self._error(
                    category,
                    "MOCK_GITHUB_UNKNOWN_OUTCOME",
                    "Remote effect persisted but response was lost",
                    context.correlation_id,
                    f"github.{operation}",
                    retryable=True,
                    unknown_outcome=True,
                    external_operation_id=external_id,
                )
            raise self._error(
                category,
                "MOCK_GITHUB_FAILURE",
                f"Scheduled mock failure: {category.value}",
                context.correlation_id,
                f"github.{operation}",
                retryable=category
                in {
                    AdapterErrorCategory.RATE_LIMIT,
                    AdapterErrorCategory.TIMEOUT,
                    AdapterErrorCategory.TRANSIENT,
                    AdapterErrorCategory.UNAVAILABLE,
                },
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
    ) -> GitHubAdapterError:
        if category is AdapterErrorCategory.UNKNOWN_OUTCOME:
            unknown_outcome = True
            retryable = True
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
                external_operation_id=external_operation_id,
            )
        )
