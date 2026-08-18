from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.cli import build_parser, main
from project_pipeline.contracts import ActionIntent, AdapterErrorCategory, ApprovalState, RiskLevel
from project_pipeline.domain.github import (
    AutonomousReviewReceipt,
    CheckConclusion,
    CheckState,
    GitHubBranchProtection,
    GitOperationState,
    GitOperationType,
    MergeGateState,
    PullRequestCheck,
    PullRequestState,
    ReviewFinding,
    github_identifier,
)
from project_pipeline.github_steward import (
    ClosedLoopLifecycle,
    GitHubStewardStore,
    LocalGitRepository,
    RepositorySteward,
    evaluate_autonomous_review,
    evaluate_branch_deletion,
    evaluate_merge_gate,
    evaluate_protection_drift,
    prove_consolidation,
)
from project_pipeline.github_steward.errors import GitHubStewardError
from project_pipeline.github_steward.merge_gate import evaluate_merge_gate as gate_fn
from tests.test_github_mock_and_service import make_repo, seeded_adapter
from tests.test_github_steward_domain import SHA1, SHA2, pull


def _receipt(**overrides: object) -> AutonomousReviewReceipt:
    payload = {
        "receipt_id": github_identifier("GHARV", "owner/repo", "7", SHA2),
        "implementer_id": "cursor-combined-agent-cycle-010",
        "reviewer_id": "cursor-independent-reviewer-cycle-010",
        "implementer_context_fingerprint": "a" * 64,
        "reviewer_context_fingerprint": "b" * 64,
        "head_sha": SHA2,
        "tree_sha": "c" * 40,
        "criterion_ids": ("AC-1",),
        "findings": (),
        "evidence_ids": ("EVID-1",),
        "conflicts": (),
        "completed_at_utc": datetime.now(UTC),
        "max_age_seconds": 3600,
    }
    payload.update(overrides)
    return AutonomousReviewReceipt.model_validate(payload)


def test_self_review_and_same_context_are_rejected():
    same_person = _receipt(reviewer_id="cursor-combined-agent-cycle-010")
    accepted, blockers = evaluate_autonomous_review(same_person, expected_head_sha=SHA2)
    assert accepted is False
    assert "self_review" in blockers
    same_ctx = _receipt(reviewer_context_fingerprint="a" * 64)
    accepted, blockers = evaluate_autonomous_review(same_ctx, expected_head_sha=SHA2)
    assert "same_context_fingerprint" in blockers


def test_stale_review_and_head_change_are_rejected():
    stale = _receipt(completed_at_utc=datetime.now(UTC) - timedelta(hours=5), max_age_seconds=60)
    _accepted, blockers = evaluate_autonomous_review(stale, expected_head_sha=SHA2)
    assert "stale_review" in blockers
    changed = _receipt(head_sha=SHA1)
    _accepted, blockers = evaluate_autonomous_review(changed, expected_head_sha=SHA2)
    assert "review_head_mismatch" in blockers


def test_tree_mismatch_and_open_blocking_finding_are_rejected():
    receipt = _receipt(
        findings=(
            ReviewFinding(
                finding_id="F-1",
                severity="BLOCKING",
                summary="unsafe",
                disposition="OPEN",
            ),
        )
    )
    _accepted, blockers = evaluate_autonomous_review(
        receipt, expected_head_sha=SHA2, expected_tree_sha="d" * 40
    )
    assert "review_tree_mismatch" in blockers
    assert "unresolved_blocking_findings" in blockers


def test_merge_gate_accepts_autonomous_review_when_github_approvals_are_zero():
    pr = pull(
        checks=(
            PullRequestCheck(
                check_id="1",
                name="tests",
                state=CheckState.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,
            ),
        )
    )
    gate = evaluate_merge_gate(
        pr,
        required_checks=("tests",),
        approvals_required=0,
        require_head_sha=SHA2,
        autonomous_review=_receipt(),
    )
    assert gate.state is MergeGateState.READY
    assert gate.autonomous_review_accepted is True


def test_merge_gate_rejects_failed_check_uncertain_merge_and_missing_review():
    uncertain = pull(mergeable=None)
    gate = gate_fn(uncertain, required_checks=("tests",), approvals_required=0)
    assert "mergeability_unknown" in gate.blockers
    assert "autonomous_review_missing" in gate.blockers
    failed = pull(
        checks=(
            PullRequestCheck(
                check_id="1",
                name="tests",
                state=CheckState.COMPLETED,
                conclusion=CheckConclusion.FAILURE,
            ),
        )
    )
    gate = gate_fn(
        failed,
        required_checks=("tests",),
        approvals_required=0,
        autonomous_review=_receipt(),
    )
    assert "required_check_failed:tests" in gate.blockers


def test_protection_drift_rejects_second_human_requirement():
    from project_pipeline.github_steward.protection_drift import (
        DEFAULT_REQUIRED_CHECK_APP_IDS,
        DEFAULT_REQUIRED_CHECKS,
    )

    drifted = GitHubBranchProtection(
        repository_slug="KevinSGarrett/ProjectPipeline",
        branch="main",
        protected=True,
        required_status_checks=DEFAULT_REQUIRED_CHECKS,
        required_status_check_app_ids=DEFAULT_REQUIRED_CHECK_APP_IDS,
        required_approving_review_count=1,
        require_code_owner_reviews=True,
        require_last_push_approval=True,
    )
    decision = evaluate_protection_drift(drifted)
    assert decision.aligned is False
    assert "human_approval_count_not_zero" in decision.drifts
    assert "code_owner_reviews_required" in decision.drifts
    aligned = drifted.model_copy(
        update={
            "required_approving_review_count": 0,
            "require_code_owner_reviews": False,
            "require_last_push_approval": False,
        }
    )
    assert evaluate_protection_drift(aligned).aligned is True


def test_protection_drift_fails_name_only_required_checks():
    from project_pipeline.github_steward.protection_drift import DEFAULT_REQUIRED_CHECKS

    name_only = GitHubBranchProtection(
        repository_slug="KevinSGarrett/ProjectPipeline",
        branch="main",
        protected=True,
        required_status_checks=DEFAULT_REQUIRED_CHECKS,
        required_status_check_app_ids=(),
        contexts_only_required_checks=True,
        required_approving_review_count=0,
    )
    decision = evaluate_protection_drift(name_only)
    assert decision.aligned is False
    assert "contexts_only_required_checks" in decision.drifts
    assert "required_check_app_id_missing" in decision.drifts
    missing_apps = name_only.model_copy(update={"contexts_only_required_checks": False})
    missing = evaluate_protection_drift(missing_apps)
    assert "required_check_app_id_missing" in missing.drifts


def test_remote_deletion_denied_for_dirty_or_unmerged_branch():
    decision = evaluate_branch_deletion(
        branch="feat/x",
        default_branch="main",
        worktree_branches=("feat/x",),
        dirty=True,
        merged_into_default=False,
        remote_only=True,
        unpublished=True,
    )
    assert decision.safe_for_cleanup is False
    codes = {item.code for item in decision.findings}
    assert "ACTIVE_WORKTREE" in codes
    assert "UNSAFE_DELETION" in codes
    assert "UNMERGED_CONTENT" in codes


def test_consolidation_requires_ancestry_and_tree_match(tmp_path):
    repo = make_repo(tmp_path)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    proof = prove_consolidation(
        repo,
        repository_slug="owner/repo",
        consolidated_head=head,
        component_heads=(head,),
        expected_tree=tree,
    )
    assert proof.eligible_to_supersede is True
    other = "a" * 40
    with pytest.raises(GitHubStewardError):
        prove_consolidation(
            repo,
            repository_slug="owner/repo",
            consolidated_head=head,
            component_heads=(other,),
        )


def test_lifecycle_persists_intent_readback_and_unknown_outcome(tmp_path):
    adapter = seeded_adapter()
    adapter.schedule_failure("merge_pull_request", AdapterErrorCategory.UNKNOWN_OUTCOME)
    db = tmp_path / "state.db"
    with GitHubStewardStore(db, Path.cwd()) as store:
        lifecycle = ClosedLoopLifecycle(remote=adapter, store=store, repository_slug="owner/repo")
        operation = lifecycle.persist_intent(
            operation_type=GitOperationType.MERGE_PULL_REQUEST,
            target="1",
            actor_id="actor:test",
            correlation_id="corr:test",
            payload={"method": "squash"},
            expected_head_sha=SHA2,
        )
        replay = lifecycle.persist_intent(
            operation_type=GitOperationType.MERGE_PULL_REQUEST,
            target="1",
            actor_id="actor:test",
            correlation_id="corr:test",
            payload={"method": "squash"},
            expected_head_sha=SHA2,
        )
        assert replay.operation_id == operation.operation_id
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
        receipt = lifecycle.apply_step(
            operation, action_intent=intent, authorization_id="auth:test", apply=True
        )
        assert receipt.state is GitOperationState.UNKNOWN_OUTCOME
        assert receipt.reconciliation_required
        adapter._pulls[1] = adapter._pulls[1].model_copy(update={"state": PullRequestState.MERGED})
        reconciled = lifecycle.reconcile_unknown(store.get_operation(operation.operation_id))
        assert reconciled.state is GitOperationState.RECONCILED
        assert lifecycle.readback_pull(1)["state"] == "MERGED"


def test_lifecycle_end_to_end_mock_merge_and_delete(tmp_path):
    adapter = seeded_adapter()
    db = tmp_path / "state.db"
    with GitHubStewardStore(db, Path.cwd()) as store:
        lifecycle = ClosedLoopLifecycle(remote=adapter, store=store, repository_slug="owner/repo")
        merge = lifecycle.persist_intent(
            operation_type=GitOperationType.MERGE_PULL_REQUEST,
            target="1",
            actor_id="actor:test",
            correlation_id="corr:test",
            payload={"method": "squash"},
            expected_head_sha=SHA2,
        )
        intent = ActionIntent(
            actor_id="actor:test",
            authority="github.steward",
            target="owner/repo",
            operation="github.merge",
            idempotency_key=merge.idempotency_key,
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:test",
            risk=RiskLevel.HIGH,
        )
        receipt = lifecycle.apply_step(
            merge, action_intent=intent, authorization_id="auth:test", apply=True
        )
        assert receipt.state is GitOperationState.APPLIED
        assert lifecycle.verify_integrated_tree(expected_tree=SHA2, observed_tree=SHA2)["matched"]
        delete = lifecycle.persist_intent(
            operation_type=GitOperationType.DELETE_BRANCH,
            target="feature/x",
            actor_id="actor:test",
            correlation_id="corr:del",
            payload={},
        )
        delete_intent = intent.model_copy(update={"idempotency_key": delete.idempotency_key})
        deleted = lifecycle.apply_step(
            delete, action_intent=delete_intent, authorization_id="auth:del", apply=True
        )
        assert deleted.state is GitOperationState.APPLIED
        assert deleted.observed_result["still_present"] is False


def test_dirty_worktree_cannot_be_removed(tmp_path):
    repo = make_repo(tmp_path)
    local = LocalGitRepository(repo)
    (repo / "dirty.txt").write_text("nope\n", encoding="utf-8")
    snapshot = local.snapshot()
    assert snapshot.dirty is True
    with pytest.raises(Exception, match="dirty worktree"):
        local.remove_worktree(repo, apply=True)


def test_cli_plan_and_protection_drift_are_read_only(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code = main(
        [
            "github",
            "protection-drift",
            "--root",
            str(Path.cwd()),
            "--repository-root",
            str(repo),
            "--database",
            str(tmp_path / "state.db"),
            "--provider",
            "mock",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code in {0, 1}
    assert "drifts" in payload
    assert "aligned" in payload


def test_cli_merge_gate_defaults_protection_drift_assert_on():
    args = build_parser().parse_args(["github", "merge-gate", "--pull-number", "1"])
    assert args.assert_protection is True
    off = build_parser().parse_args(
        ["github", "merge-gate", "--pull-number", "1", "--no-assert-protection"]
    )
    assert off.assert_protection is False


def test_merge_gate_default_evaluates_protection_drift_predicates(tmp_path):
    from project_pipeline.github_steward.protection_drift import DEFAULT_REQUIRED_CHECKS

    repo = make_repo(tmp_path)
    adapter = seeded_adapter()
    adapter.repository_slug = "KevinSGarrett/ProjectPipeline"
    adapter.set_branch_protection(
        GitHubBranchProtection(
            repository_slug="KevinSGarrett/ProjectPipeline",
            branch="main",
            protected=True,
            required_status_checks=DEFAULT_REQUIRED_CHECKS,
            required_status_check_app_ids=(15368, 15368, 15368, None),
            required_approving_review_count=1,
            require_code_owner_reviews=False,
            require_last_push_approval=False,
        )
    )
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        steward = RepositorySteward(local=LocalGitRepository(repo), remote=adapter, store=store)
        gate = steward.merge_gate("KevinSGarrett/ProjectPipeline", 1)
    assert "protection_changed" in gate.blockers
    assert "human_approval_count_not_zero" in gate.protection_drift


def test_unknown_outcome_is_reconciled_not_retried(tmp_path):
    adapter = seeded_adapter()
    adapter.schedule_failure("merge_pull_request", AdapterErrorCategory.UNKNOWN_OUTCOME)
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        lifecycle = ClosedLoopLifecycle(remote=adapter, store=store, repository_slug="owner/repo")
        operation = lifecycle.persist_intent(
            operation_type=GitOperationType.MERGE_PULL_REQUEST,
            target="1",
            actor_id="actor:test",
            correlation_id="corr:test",
            payload={"method": "squash"},
            expected_head_sha=SHA2,
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
        first = lifecycle.apply_step(
            operation, action_intent=intent, authorization_id="auth:test", apply=True
        )
        assert first.state is GitOperationState.UNKNOWN_OUTCOME
        stored = store.get_operation(operation.operation_id)
        with pytest.raises(GitHubStewardError, match="unknown-outcome"):
            lifecycle.apply_step(
                stored, action_intent=intent, authorization_id="auth:test", apply=True
            )
        adapter._pulls[1] = adapter._pulls[1].model_copy(update={"state": PullRequestState.MERGED})
        reconciled = lifecycle.reconcile_unknown(stored)
        assert reconciled.state is GitOperationState.RECONCILED


def test_unknown_delete_reconciles_without_second_delete(tmp_path):
    adapter = seeded_adapter()
    adapter.schedule_failure("delete_branch", AdapterErrorCategory.UNKNOWN_OUTCOME)
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        lifecycle = ClosedLoopLifecycle(remote=adapter, store=store, repository_slug="owner/repo")
        operation = lifecycle.persist_intent(
            operation_type=GitOperationType.DELETE_BRANCH,
            target="feature/x",
            actor_id="actor:test",
            correlation_id="corr:del",
            payload={},
        )
        intent = ActionIntent(
            actor_id="actor:test",
            authority="github.steward",
            target="owner/repo",
            operation="github.merge",
            idempotency_key=operation.idempotency_key,
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:del",
            risk=RiskLevel.HIGH,
        )
        receipt = lifecycle.apply_step(
            operation, action_intent=intent, authorization_id="auth:del", apply=True
        )
        assert receipt.state is GitOperationState.UNKNOWN_OUTCOME
        assert "feature/x" not in {item.name for item in adapter.iter_branches("owner/repo")}
        reconciled = lifecycle.reconcile_unknown(store.get_operation(operation.operation_id))
        assert reconciled.state is GitOperationState.RECONCILED
        assert adapter.calls.count(("delete_branch", "feature/x")) == 1


def test_apply_step_refuses_merge_when_gate_blocked(tmp_path):
    adapter = seeded_adapter()
    adapter.set_branch_protection(
        GitHubBranchProtection(
            repository_slug="owner/repo",
            branch="main",
            protected=True,
            required_status_checks=("tests",),
            required_approving_review_count=0,
        )
    )
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        lifecycle = ClosedLoopLifecycle(remote=adapter, store=store, repository_slug="owner/repo")
        operation = lifecycle.persist_intent(
            operation_type=GitOperationType.MERGE_PULL_REQUEST,
            target="1",
            actor_id="actor:test",
            correlation_id="corr:test",
            payload={"method": "squash"},
            expected_head_sha=SHA2,
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
        with pytest.raises(GitHubStewardError, match="Merge Gate is blocked"):
            lifecycle.apply_step(
                operation, action_intent=intent, authorization_id="auth:test", apply=True
            )


def test_service_merge_gate_rejects_changed_head_with_receipt(tmp_path):
    repo = make_repo(tmp_path)
    adapter = seeded_adapter()
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        steward = RepositorySteward(local=LocalGitRepository(repo), remote=adapter, store=store)
        gate = steward.merge_gate(
            "owner/repo",
            1,
            expected_head_sha=SHA1,
            autonomous_review=_receipt(),
        )
        assert "pull_request_head_changed" in gate.blockers


def test_apply_merge_refuses_unknown_outcome_retry(tmp_path):
    repo = make_repo(tmp_path)
    adapter = seeded_adapter()
    with GitHubStewardStore(tmp_path / "state.db", Path.cwd()) as store:
        steward = RepositorySteward(local=LocalGitRepository(repo), remote=adapter, store=store)
        gate, operation = steward.plan_merge(
            "owner/repo",
            1,
            actor_id="actor:test",
            correlation_id="corr:unknown",
            expected_head_sha=SHA2,
            autonomous_review=_receipt(),
        )
        store.save_operation(
            operation.model_copy(update={"state": GitOperationState.UNKNOWN_OUTCOME})
        )
        intent = ActionIntent(
            actor_id="actor:test",
            authority="github.steward",
            target="owner/repo",
            operation="github.merge",
            idempotency_key=operation.idempotency_key,
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:unknown",
            risk=RiskLevel.HIGH,
        )
        with pytest.raises(GitHubStewardError, match="reconciled before any retry"):
            steward.apply_merge(operation, gate, action_intent=intent, authorization_id="auth:x")


def test_autonomous_review_age_is_capped_by_policy_constant():
    from project_pipeline.github_steward.autonomous_review import (
        MAX_AUTONOMOUS_REVIEW_AGE_SECONDS,
        evaluate_autonomous_review,
    )

    old = _receipt(
        completed_at_utc=datetime.now(UTC)
        - timedelta(seconds=MAX_AUTONOMOUS_REVIEW_AGE_SECONDS + 5),
        max_age_seconds=86400,
    )
    accepted, blockers = evaluate_autonomous_review(old, expected_head_sha=SHA2)
    assert accepted is False
    assert "stale_review" in blockers
