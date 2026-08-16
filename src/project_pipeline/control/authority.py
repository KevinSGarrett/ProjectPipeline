from __future__ import annotations

from enum import StrEnum
from typing import Literal

from project_pipeline.domain.base import DomainModel


class RecommendationDisposition(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class RecommendationAuthorityDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    recommendation_id: str
    disposition: RecommendationDisposition
    may_apply: bool
    canonical_authority: Literal["PROJECT_PIPELINE"] = "PROJECT_PIPELINE"
    reasons: tuple[str, ...]


def evaluate_recommendation_authority(
    recommendation_id: str,
    *,
    conflicts_with_canonical_plan: bool = False,
    conflicts_with_policy: bool = False,
) -> RecommendationAuthorityDecision:
    """Fail closed when an advisory recommendation conflicts with canonical authority.

    Recommendations never acquire state authority by themselves. Policy conflicts are
    rejected. Plan conflicts are escalated for an explicit authority decision rather
    than being silently applied.
    """
    if conflicts_with_policy:
        return RecommendationAuthorityDecision(
            recommendation_id=recommendation_id,
            disposition=RecommendationDisposition.REJECT,
            may_apply=False,
            reasons=("recommendation conflicts with governing policy",),
        )
    if conflicts_with_canonical_plan:
        return RecommendationAuthorityDecision(
            recommendation_id=recommendation_id,
            disposition=RecommendationDisposition.ESCALATE,
            may_apply=False,
            reasons=(
                "recommendation conflicts with the canonical plan and requires explicit reconciliation",
            ),
        )
    return RecommendationAuthorityDecision(
        recommendation_id=recommendation_id,
        disposition=RecommendationDisposition.ACCEPT,
        may_apply=True,
        reasons=("recommendation is aligned with canonical plan and policy",),
    )
