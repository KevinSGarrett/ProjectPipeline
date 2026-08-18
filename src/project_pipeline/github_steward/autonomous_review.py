from __future__ import annotations

from datetime import UTC, datetime

from project_pipeline.domain.github import AutonomousReviewReceipt


def evaluate_autonomous_review(
    receipt: AutonomousReviewReceipt,
    *,
    expected_head_sha: str,
    expected_tree_sha: str | None = None,
    now: datetime | None = None,
) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    if receipt.implementer_id == receipt.reviewer_id:
        blockers.append("self_review")
    if receipt.implementer_context_fingerprint == receipt.reviewer_context_fingerprint:
        blockers.append("same_context_fingerprint")
    if receipt.conflicts:
        blockers.append("review_conflicts")
    if receipt.reviewer_authority != "READ_ONLY":
        blockers.append("reviewer_not_read_only")
    if receipt.head_sha != expected_head_sha.lower():
        blockers.append("review_head_mismatch")
    if expected_tree_sha and receipt.tree_sha != expected_tree_sha.lower():
        blockers.append("review_tree_mismatch")
    if receipt.blocking_finding_count:
        blockers.append("unresolved_blocking_findings")
    current = now or datetime.now(UTC)
    observed = receipt.completed_at_utc
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    age = (current - observed).total_seconds()
    if age > receipt.max_age_seconds:
        blockers.append("stale_review")
    if age < 0:
        blockers.append("review_timestamp_in_future")
    return (not blockers, tuple(sorted(set(blockers))))
