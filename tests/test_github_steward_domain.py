from __future__ import annotations

from datetime import UTC, datetime

import pytest

from project_pipeline.domain.github import (
    CheckConclusion,
    CheckState,
    GitHubBranchProtection,
    MergeGateState,
    OwnershipKind,
    PullRequestCheck,
    PullRequestReview,
    PullRequestSnapshot,
    PullRequestState,
    ReviewState,
    github_identifier,
)
from project_pipeline.github_steward.merge_gate import evaluate_merge_gate
from project_pipeline.github_steward.ownership import OwnershipRegistry

SHA1 = "a" * 40
SHA2 = "b" * 40


def pull(*, draft=False, mergeable=True, reviews=(), checks=()):
    return PullRequestSnapshot(
        pull_request_id=github_identifier("GHPR", "owner/repo", "7", SHA2),
        repository_slug="owner/repo",
        number=7,
        title="Implement governed repository stewardship",
        state=PullRequestState.OPEN,
        draft=draft,
        base_branch="main",
        head_branch="feature/pp-7",
        base_sha=SHA1,
        head_sha=SHA2,
        mergeable=mergeable,
        reviews=reviews,
        checks=checks,
    )


def test_merge_gate_requires_checks_and_approval():
    pr = pull(
        reviews=(
            PullRequestReview(
                review_id="1",
                author="reviewer",
                state=ReviewState.APPROVED,
                submitted_at_utc=datetime.now(UTC),
            ),
        ),
        checks=(
            PullRequestCheck(
                check_id="1",
                name="tests",
                state=CheckState.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,
            ),
        ),
    )
    gate = evaluate_merge_gate(
        pr, required_checks=("tests",), approvals_required=1, require_head_sha=SHA2
    )
    assert gate.state is MergeGateState.READY
    assert gate.approvals_observed == 1


def test_merge_gate_blocks_draft_failure_and_changes_requested():
    pr = pull(
        draft=True,
        reviews=(
            PullRequestReview(
                review_id="1", author="reviewer", state=ReviewState.CHANGES_REQUESTED
            ),
        ),
        checks=(
            PullRequestCheck(
                check_id="1",
                name="tests",
                state=CheckState.COMPLETED,
                conclusion=CheckConclusion.FAILURE,
            ),
        ),
    )
    gate = evaluate_merge_gate(pr, required_checks=("tests",), approvals_required=1)
    assert gate.state is MergeGateState.BLOCKED
    assert "pull_request_is_draft" in gate.blockers
    assert "changes_requested" in gate.blockers
    assert "required_check_failed:tests" in gate.blockers


def test_merge_gate_detects_head_change_and_missing_check():
    gate = evaluate_merge_gate(
        pull(), required_checks=("required",), approvals_required=0, require_head_sha=SHA1
    )
    assert "pull_request_head_changed" in gate.blockers
    assert "required_check_missing:required" in gate.blockers


def test_incomplete_check_rejects_final_conclusion():
    with pytest.raises(ValueError):
        PullRequestCheck(
            check_id="1",
            name="tests",
            state=CheckState.IN_PROGRESS,
            conclusion=CheckConclusion.SUCCESS,
        )


def test_ownership_registry_rejects_overlapping_directories():
    registry = OwnershipRegistry()
    first = registry.acquire(
        repository_slug="owner/repo",
        resource_kind=OwnershipKind.DIRECTORY,
        resource="src/project_pipeline",
        owner_task_id="PP-TASK-1",
        workspace_id="ws-1",
    )
    assert first.resource == "src/project_pipeline"
    with pytest.raises(ValueError, match="ownership conflict"):
        registry.acquire(
            repository_slug="owner/repo",
            resource_kind=OwnershipKind.DIRECTORY,
            resource="src/project_pipeline/github_steward",
            owner_task_id="PP-TASK-2",
            workspace_id="ws-2",
        )


def test_ownership_registry_allows_same_owner_and_distinct_resource_types():
    registry = OwnershipRegistry()
    registry.acquire(
        repository_slug="owner/repo",
        resource_kind=OwnershipKind.FILE,
        resource="src/a.py",
        owner_task_id="PP-TASK-1",
        workspace_id="ws-1",
    )
    registry.acquire(
        repository_slug="owner/repo",
        resource_kind=OwnershipKind.FILE,
        resource="src/a.py",
        owner_task_id="PP-TASK-1",
        workspace_id="ws-2",
    )
    registry.acquire(
        repository_slug="owner/repo",
        resource_kind=OwnershipKind.PORT,
        resource="8000",
        owner_task_id="PP-TASK-2",
        workspace_id="ws-2",
    )
    assert len(registry.active()) == 3


def test_branch_protection_accepts_explicit_requirements():
    p = GitHubBranchProtection(
        repository_slug="owner/repo",
        branch="main",
        protected=True,
        required_status_checks=("tests", "lint"),
        required_approving_review_count=2,
        require_code_owner_reviews=True,
    )
    assert p.required_approving_review_count == 2
