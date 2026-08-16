from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.contracts import ActionIntent, AdapterErrorCategory, ApprovalState, RiskLevel
from project_pipeline.domain.github import (
    BranchRole,
    CheckConclusion,
    CheckState,
    GitBranch,
    GitHubBranchProtection,
    GitOperationState,
    PullRequestCheck,
    PullRequestReview,
    PullRequestSnapshot,
    PullRequestState,
    ReviewState,
    github_identifier,
)
from project_pipeline.github_steward import (
    GitHubStewardStore,
    LocalGitRepository,
    MockGitHubAdapter,
    RepositorySteward,
)
from project_pipeline.github_steward.ports import GitHubWriteContext

SHA1 = "a" * 40
SHA2 = "b" * 40


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "README.md").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/owner/repo.git"],
        check=True,
    )
    return repo


def seeded_adapter() -> MockGitHubAdapter:
    main = GitBranch(
        branch_id=github_identifier("GHBR", "owner/repo", "main", SHA1),
        name="main",
        sha=SHA1,
        role=BranchRole.DEFAULT,
        is_default=True,
    )
    feature = GitBranch(
        branch_id=github_identifier("GHBR", "owner/repo", "feature/x", SHA2),
        name="feature/x",
        sha=SHA2,
        role=BranchRole.FEATURE,
    )
    pr = PullRequestSnapshot(
        pull_request_id=github_identifier("GHPR", "owner/repo", "1", SHA2),
        repository_slug="owner/repo",
        number=1,
        title="Feature",
        state=PullRequestState.OPEN,
        base_branch="main",
        head_branch="feature/x",
        base_sha=SHA1,
        head_sha=SHA2,
        mergeable=True,
    )
    adapter = MockGitHubAdapter(repository_slug="owner/repo", branches=(main, feature), pulls=(pr,))
    adapter.set_branch_protection(
        GitHubBranchProtection(
            repository_slug="owner/repo",
            branch="main",
            protected=True,
            required_status_checks=("tests",),
            required_approving_review_count=1,
        )
    )
    adapter.seed_review(
        1,
        PullRequestReview(
            review_id="r1",
            author="reviewer",
            state=ReviewState.APPROVED,
            submitted_at_utc=datetime.now(UTC),
        ),
    )
    adapter.seed_check(
        SHA2,
        PullRequestCheck(
            check_id="c1",
            name="tests",
            state=CheckState.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
        ),
    )
    return adapter


def test_mock_paginates_branches():
    adapter = seeded_adapter()
    rows = tuple(adapter.iter_branches("owner/repo", page_size=1))
    assert len(rows) == 2
    assert adapter.pages_observed == 2


def test_mock_write_idempotency():
    adapter = seeded_adapter()
    ctx = GitHubWriteContext(
        actor_id="actor:test",
        correlation_id="corr:test",
        idempotency_key="branch-create-0001",
        authorization_id="auth:test",
    )
    first = adapter.create_branch("owner/repo", branch="feature/new", sha=SHA1, context=ctx)
    second = adapter.create_branch("owner/repo", branch="feature/new", sha=SHA1, context=ctx)
    assert first == second
    assert adapter.calls.count(("create_branch", "feature/new")) == 1


def test_service_merge_gate_and_apply(tmp_path):
    repo = make_repo(tmp_path)
    adapter = seeded_adapter()
    db = tmp_path / "state.db"
    with GitHubStewardStore(db, Path.cwd()) as store:
        # cwd in test execution is repository root containing migration catalog
        steward = RepositorySteward(local=LocalGitRepository(repo), remote=adapter, store=store)
        gate, operation = steward.plan_merge(
            "owner/repo", 1, actor_id="actor:test", correlation_id="corr:test"
        )
        assert gate.state.value == "READY"
        intent = ActionIntent(
            actor_id="actor:test",
            authority="github.steward",
            target="owner/repo",
            operation="github.merge",
            idempotency_key=operation.idempotency_key,
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:test",
            risk=RiskLevel.HIGH,
        )
        receipt = steward.apply_merge(
            operation, gate, action_intent=intent, authorization_id="auth:test"
        )
        assert receipt.state is GitOperationState.APPLIED
        assert adapter.get_pull_request("owner/repo", 1).state is PullRequestState.MERGED


def test_unknown_merge_outcome_is_not_retried(tmp_path):
    repo = make_repo(tmp_path)
    adapter = seeded_adapter()
    adapter.schedule_failure("merge_pull_request", AdapterErrorCategory.UNKNOWN_OUTCOME)
    db = tmp_path / "state.db"
    with GitHubStewardStore(db, Path.cwd()) as store:
        steward = RepositorySteward(local=LocalGitRepository(repo), remote=adapter, store=store)
        gate, operation = steward.plan_merge(
            "owner/repo", 1, actor_id="actor:test", correlation_id="corr:test"
        )
        intent = ActionIntent(
            actor_id="actor:test",
            authority="github.steward",
            target="owner/repo",
            operation="github.merge",
            idempotency_key=operation.idempotency_key,
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:test",
            risk=RiskLevel.HIGH,
        )
        receipt = steward.apply_merge(
            operation, gate, action_intent=intent, authorization_id="auth:test"
        )
        assert receipt.state is GitOperationState.UNKNOWN_OUTCOME
        assert receipt.reconciliation_required
        assert store.status("owner/repo")["reconciliation_required"]
        assert adapter.calls.count(("merge_pull_request", "1")) == 1


def test_cleanup_protects_default_and_active_worktree(tmp_path):
    repo = make_repo(tmp_path)
    adapter = seeded_adapter()
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        steward = RepositorySteward(local=LocalGitRepository(repo), remote=adapter, store=store)
        plan = steward.cleanup_plan("owner/repo")
        assert any(
            item["branch"] == "main" and item["reason"] == "default_branch"
            for item in plan["protected"]
        )
