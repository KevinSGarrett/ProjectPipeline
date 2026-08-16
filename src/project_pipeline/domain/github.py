from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now

HEX_SHA = re.compile(r"^[0-9a-f]{7,64}$")
REPOSITORY_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_RECORD_ID = re.compile(
    r"^(GHREP|GHBR|GHWT|GHOWN|GHPR|GHREV|GHCHK|GHGATE|GHOP|GHREC)-[A-F0-9]{20}$"
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def github_identifier(
    prefix: Literal[
        "GHREP", "GHBR", "GHWT", "GHOWN", "GHPR", "GHREV", "GHCHK", "GHGATE", "GHOP", "GHREC"
    ],
    *parts: str,
) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("GitHub stewardship identifier parts must be non-empty")
    digest = (
        hashlib.sha256("\x1f".join(str(part).strip() for part in parts).encode("utf-8"))
        .hexdigest()[:20]
        .upper()
    )
    return f"{prefix}-{digest}"


class BranchRole(StrEnum):
    DEFAULT = "DEFAULT"
    FEATURE = "FEATURE"
    RELEASE = "RELEASE"
    HOTFIX = "HOTFIX"
    UNKNOWN = "UNKNOWN"


class WorktreeState(StrEnum):
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    DETACHED = "DETACHED"
    MISSING = "MISSING"


class OwnershipKind(StrEnum):
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    SCHEMA = "SCHEMA"
    DATABASE = "DATABASE"
    PORT = "PORT"
    ENVIRONMENT = "ENVIRONMENT"
    REPOSITORY = "REPOSITORY"


class OwnershipState(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class ReviewState(StrEnum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"
    PENDING = "PENDING"


class CheckState(StrEnum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"


class CheckConclusion(StrEnum):
    SUCCESS = "SUCCESS"
    NEUTRAL = "NEUTRAL"
    SKIPPED = "SKIPPED"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    STALE = "STALE"
    STARTUP_FAILURE = "STARTUP_FAILURE"
    UNKNOWN = "UNKNOWN"


class PullRequestState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"


class MergeGateState(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class GitOperationState(StrEnum):
    PLANNED = "PLANNED"
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    RECONCILED = "RECONCILED"
    REJECTED = "REJECTED"


class GitOperationType(StrEnum):
    CREATE_BRANCH = "CREATE_BRANCH"
    CREATE_PULL_REQUEST = "CREATE_PULL_REQUEST"
    UPDATE_PULL_REQUEST = "UPDATE_PULL_REQUEST"
    MERGE_PULL_REQUEST = "MERGE_PULL_REQUEST"
    DELETE_BRANCH = "DELETE_BRANCH"
    CREATE_WORKTREE = "CREATE_WORKTREE"
    REMOVE_WORKTREE = "REMOVE_WORKTREE"
    RELEASE_OWNERSHIP = "RELEASE_OWNERSHIP"


class GuardianFindingSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class GitRepositorySnapshot(DomainModel):
    repository_id: str
    repository_slug: str
    root_path: str
    default_branch: str
    head_sha: str
    current_branch: str | None
    detached_head: bool = False
    dirty: bool = False
    staged_paths: tuple[str, ...] = ()
    unstaged_paths: tuple[str, ...] = ()
    untracked_paths: tuple[str, ...] = ()
    remotes: dict[str, str] = Field(default_factory=dict)
    captured_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("repository_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHREP-"):
            raise ValueError("invalid repository snapshot identifier")
        return value

    @field_validator("repository_slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        if not REPOSITORY_SLUG.fullmatch(value):
            raise ValueError("repository_slug must be owner/name")
        return value

    @field_validator("head_sha")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if not HEX_SHA.fullmatch(value.lower()):
            raise ValueError("head_sha must be a hexadecimal Git object id")
        return value.lower()


class GitBranch(DomainModel):
    branch_id: str
    name: str = Field(min_length=1, max_length=255)
    sha: str
    role: BranchRole = BranchRole.UNKNOWN
    is_default: bool = False
    is_current: bool = False
    upstream: str | None = None
    ahead: int = Field(default=0, ge=0)
    behind: int = Field(default=0, ge=0)
    merged_into_default: bool | None = None
    protected: bool | None = None

    @field_validator("branch_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHBR-"):
            raise ValueError("invalid branch identifier")
        return value

    @field_validator("sha")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if not HEX_SHA.fullmatch(value.lower()):
            raise ValueError("branch sha must be hexadecimal")
        return value.lower()


class GitWorktree(DomainModel):
    worktree_id: str
    path: str = Field(min_length=1, max_length=2000)
    head_sha: str
    branch: str | None = None
    state: WorktreeState
    prunable: bool = False
    locked: bool = False
    lock_reason: str | None = None
    owner_task_id: str | None = None

    @field_validator("worktree_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHWT-"):
            raise ValueError("invalid worktree identifier")
        return value

    @field_validator("head_sha")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if not HEX_SHA.fullmatch(value.lower()):
            raise ValueError("worktree head sha must be hexadecimal")
        return value.lower()


class ResourceOwnershipClaim(DomainModel):
    ownership_id: str
    repository_slug: str
    resource_kind: OwnershipKind
    resource: str = Field(min_length=1, max_length=2000)
    owner_task_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    state: OwnershipState = OwnershipState.ACTIVE
    acquired_at_utc: datetime = Field(default_factory=utc_now)
    expires_at_utc: datetime | None = None

    @field_validator("ownership_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHOWN-"):
            raise ValueError("invalid ownership identifier")
        return value

    @model_validator(mode="after")
    def validate_expiry(self) -> ResourceOwnershipClaim:
        if self.expires_at_utc is not None and self.expires_at_utc <= self.acquired_at_utc:
            raise ValueError("ownership expiry must follow acquisition")
        return self


class BranchGuardianFinding(DomainModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,80}$")
    severity: GuardianFindingSeverity
    message: str = Field(min_length=1, max_length=2000)
    remediation: str = Field(min_length=1, max_length=2000)


class BranchGuardianDecision(DomainModel):
    repository_slug: str
    branch: str | None
    safe_for_work: bool
    safe_for_cleanup: bool
    findings: tuple[BranchGuardianFinding, ...]
    evaluated_at_utc: datetime = Field(default_factory=utc_now)


class PullRequestReview(DomainModel):
    review_id: str
    review_node_id: str | None = None
    author: str
    state: ReviewState
    commit_sha: str | None = None
    submitted_at_utc: datetime | None = None


class PullRequestCheck(DomainModel):
    check_id: str
    name: str
    state: CheckState
    conclusion: CheckConclusion | None = None
    required: bool = False
    details_url: str | None = None

    @model_validator(mode="after")
    def validate_completion(self) -> PullRequestCheck:
        if self.state is CheckState.COMPLETED and self.conclusion is None:
            raise ValueError("completed check requires a conclusion")
        if self.state is not CheckState.COMPLETED and self.conclusion not in {
            None,
            CheckConclusion.UNKNOWN,
        }:
            raise ValueError("incomplete check cannot have a final conclusion")
        return self


class PullRequestSnapshot(DomainModel):
    pull_request_id: str
    repository_slug: str
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=1000)
    state: PullRequestState
    draft: bool = False
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str
    mergeable: bool | None = None
    mergeable_state: str | None = None
    author: str | None = None
    changed_files: int = Field(default=0, ge=0)
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
    reviews: tuple[PullRequestReview, ...] = ()
    checks: tuple[PullRequestCheck, ...] = ()
    updated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("pull_request_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHPR-"):
            raise ValueError("invalid pull request identifier")
        return value

    @field_validator("base_sha", "head_sha")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if not HEX_SHA.fullmatch(value.lower()):
            raise ValueError("pull request sha must be hexadecimal")
        return value.lower()


class MergeGateDecision(DomainModel):
    gate_id: str
    repository_slug: str
    pull_number: int = Field(ge=1)
    head_sha: str
    state: MergeGateState
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()
    observed_checks: tuple[str, ...] = ()
    approvals_required: int = Field(default=1, ge=0)
    approvals_observed: int = Field(default=0, ge=0)
    evaluated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("gate_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHGATE-"):
            raise ValueError("invalid merge gate identifier")
        return value


class GitHubAdapterCapabilities(DomainModel):
    provider: str
    api_version: str
    supports_branches: bool = True
    supports_pull_requests: bool = True
    supports_reviews: bool = True
    supports_checks: bool = True
    supports_merge: bool = True
    supports_delete_branch: bool = True
    supports_branch_protection: bool = True
    maximum_page_size: int = Field(default=100, ge=1, le=100)


class GitHubRepositoryMetadata(DomainModel):
    repository_slug: str
    repository_id: str
    default_branch: str
    private: bool = False
    archived: bool = False
    disabled: bool = False
    allow_merge_commit: bool | None = None
    allow_squash_merge: bool | None = None
    allow_rebase_merge: bool | None = None


class GitHubBranchProtection(DomainModel):
    repository_slug: str
    branch: str
    protected: bool
    required_status_checks: tuple[str, ...] = ()
    required_approving_review_count: int = Field(default=0, ge=0)
    dismiss_stale_reviews: bool = False
    require_code_owner_reviews: bool = False
    enforce_admins: bool = False


class GitHubOperation(DomainModel):
    operation_id: str
    operation_type: GitOperationType
    repository_slug: str
    target: str
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=255)
    state: GitOperationState = GitOperationState.PLANNED
    expected_head_sha: str | None = None
    authorization_id: str | None = None
    actor_id: str
    correlation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    observed_result: dict[str, Any] | None = None
    created_at_utc: datetime = Field(default_factory=utc_now)
    updated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("operation_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHOP-"):
            raise ValueError("invalid GitHub operation identifier")
        return value

    @classmethod
    def create(
        cls,
        *,
        operation_type: GitOperationType,
        repository_slug: str,
        target: str,
        idempotency_key: str,
        actor_id: str,
        correlation_id: str,
        payload: dict[str, Any] | None = None,
        expected_head_sha: str | None = None,
    ) -> GitHubOperation:
        normalized = payload or {}
        fingerprint = hashlib.sha256(
            _canonical(
                {
                    "type": operation_type.value,
                    "repo": repository_slug,
                    "target": target,
                    "payload": normalized,
                    "expected": expected_head_sha,
                }
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            operation_id=github_identifier(
                "GHOP", operation_type.value, repository_slug, target, fingerprint
            ),
            operation_type=operation_type,
            repository_slug=repository_slug,
            target=target,
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload=normalized,
            expected_head_sha=expected_head_sha,
        )


class GitHubOperationReceipt(DomainModel):
    receipt_id: str
    operation_id: str
    state: GitOperationState
    provider: str
    external_identifier: str | None = None
    observed_result: dict[str, Any] | None = None
    reconciliation_required: bool = False
    created_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("receipt_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not GITHUB_RECORD_ID.fullmatch(value) or not value.startswith("GHREC-"):
            raise ValueError("invalid GitHub receipt identifier")
        return value
