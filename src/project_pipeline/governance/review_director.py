"""Review Director coordinates independent review and never implements."""

from __future__ import annotations

from typing import Any

from project_pipeline.domain.github import AutonomousReviewReceipt
from project_pipeline.github_steward.autonomous_review import evaluate_autonomous_review


def coordinate_independent_review(
    receipt: AutonomousReviewReceipt,
    *,
    expected_head_sha: str,
    expected_tree_sha: str,
    implementer_id: str,
) -> dict[str, Any]:
    """Accept only a distinct read-only reviewer bound to the exact head/tree."""

    if receipt.reviewer_id == implementer_id or receipt.implementer_id == receipt.reviewer_id:
        return {
            "accepted": False,
            "implemented": False,
            "reviewer_authority": receipt.reviewer_authority,
            "blockers": ("self_review",),
            "user_action_required": False,
        }
    accepted, blockers = evaluate_autonomous_review(
        receipt,
        expected_head_sha=expected_head_sha,
        expected_tree_sha=expected_tree_sha,
    )
    return {
        "accepted": accepted,
        "implemented": False,
        "reviewer_authority": receipt.reviewer_authority,
        "receipt_id": receipt.receipt_id,
        "blockers": blockers,
        "user_action_required": False,
    }
