from __future__ import annotations

from project_pipeline.domain.github import (
    BranchGuardianDecision,
    CheckConclusion,
    CheckState,
    MergeGateDecision,
    MergeGateState,
    PullRequestSnapshot,
    PullRequestState,
    ReviewState,
    github_identifier,
)

_SUCCESS_CHECKS = {CheckConclusion.SUCCESS, CheckConclusion.NEUTRAL, CheckConclusion.SKIPPED}


def evaluate_merge_gate(
    pull_request: PullRequestSnapshot,
    *,
    guardian: BranchGuardianDecision | None = None,
    required_checks: tuple[str, ...] = (),
    approvals_required: int = 1,
    require_head_sha: str | None = None,
) -> MergeGateDecision:
    blockers: list[str] = []
    warnings: list[str] = []
    if pull_request.state is not PullRequestState.OPEN:
        blockers.append("pull_request_not_open")
    if pull_request.draft:
        blockers.append("pull_request_is_draft")
    if pull_request.mergeable is False:
        blockers.append("pull_request_has_merge_conflict")
    if pull_request.mergeable is None:
        warnings.append("mergeability_not_yet_known")
    if require_head_sha and pull_request.head_sha != require_head_sha.lower():
        blockers.append("pull_request_head_changed")

    latest_review_by_author = {}
    for review in sorted(
        pull_request.reviews, key=lambda item: item.submitted_at_utc or pull_request.updated_at_utc
    ):
        latest_review_by_author[review.author] = review
    approvals = sum(
        1 for review in latest_review_by_author.values() if review.state is ReviewState.APPROVED
    )
    if any(
        review.state is ReviewState.CHANGES_REQUESTED for review in latest_review_by_author.values()
    ):
        blockers.append("changes_requested")
    if approvals < approvals_required:
        blockers.append("insufficient_approvals")

    by_name = {check.name: check for check in pull_request.checks}
    for name in required_checks:
        check = by_name.get(name)
        if check is None:
            blockers.append(f"required_check_missing:{name}")
        elif check.state is not CheckState.COMPLETED:
            blockers.append(f"required_check_incomplete:{name}")
        elif check.conclusion not in _SUCCESS_CHECKS:
            blockers.append(f"required_check_failed:{name}")

    if guardian is not None and not guardian.safe_for_work:
        blockers.append("branch_guardian_blocked")
    state = MergeGateState.BLOCKED if blockers else MergeGateState.READY
    return MergeGateDecision(
        gate_id=github_identifier(
            "GHGATE",
            pull_request.repository_slug,
            str(pull_request.number),
            pull_request.head_sha,
            state.value,
        ),
        repository_slug=pull_request.repository_slug,
        pull_number=pull_request.number,
        head_sha=pull_request.head_sha,
        state=state,
        blockers=tuple(sorted(set(blockers))),
        warnings=tuple(sorted(set(warnings))),
        required_checks=required_checks,
        observed_checks=tuple(sorted(by_name)),
        approvals_required=approvals_required,
        approvals_observed=approvals,
    )
