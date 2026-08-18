from __future__ import annotations

from typing import Any

from project_pipeline.domain.github import (
    GitHubBranchProtection,
    ProtectionDriftDecision,
    github_identifier,
)

DEFAULT_REQUIRED_CHECKS = (
    "Python 3.11 verification",
    "Python 3.13 verification",
    "dependency-audit",
    "Python CodeQL",
)


def expected_main_protection(
    repository_slug: str,
    *,
    branch: str = "main",
    required_checks: tuple[str, ...] = DEFAULT_REQUIRED_CHECKS,
) -> dict[str, Any]:
    return {
        "repository_slug": repository_slug,
        "branch": branch,
        "protected": True,
        "required_status_checks": list(required_checks),
        "required_status_checks_strict": True,
        "reviews_object_present": True,
        "required_approving_review_count": 0,
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
        "require_last_push_approval": False,
        "enforce_admins": True,
        "require_linear_history": True,
        "require_conversation_resolution": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


PROJECT_MAIN = ("KevinSGarrett/ProjectPipeline", "main")


def evaluate_protection_drift(
    observed: GitHubBranchProtection,
    *,
    required_checks: tuple[str, ...] | None = None,
    policy: str = "auto",
) -> ProtectionDriftDecision:
    full_policy = policy == "autonomous_main" or (
        policy == "auto" and (observed.repository_slug, observed.branch) == PROJECT_MAIN
    )
    expected_checks = required_checks or (
        DEFAULT_REQUIRED_CHECKS if full_policy else observed.required_status_checks
    )
    expected = expected_main_protection(
        observed.repository_slug, branch=observed.branch, required_checks=expected_checks
    )
    if not full_policy:
        expected["required_approving_review_count"] = observed.required_approving_review_count
        expected["require_code_owner_reviews"] = observed.require_code_owner_reviews
        expected["require_last_push_approval"] = False
        expected["enforce_admins"] = observed.enforce_admins
        expected["require_linear_history"] = observed.require_linear_history
        expected["require_conversation_resolution"] = observed.require_conversation_resolution
        expected["dismiss_stale_reviews"] = observed.dismiss_stale_reviews
    drifts: list[str] = []
    if not observed.protected:
        drifts.append("branch_unprotected")
    if not observed.reviews_object_present:
        drifts.append("reviews_object_absent")
    if not observed.required_status_checks:
        drifts.append("required_checks_empty")
    elif tuple(sorted(observed.required_status_checks)) != tuple(sorted(expected_checks)):
        drifts.append("required_checks_drifted")
    if observed.allow_force_pushes:
        drifts.append("force_pushes_allowed")
    if observed.allow_deletions:
        drifts.append("default_branch_deletion_allowed")
    if observed.require_last_push_approval:
        drifts.append("last_push_approval_required")
    if full_policy:
        if not observed.required_status_checks_strict:
            drifts.append("strict_checks_disabled")
        if observed.required_approving_review_count != 0:
            drifts.append("human_approval_count_not_zero")
        if observed.require_code_owner_reviews:
            drifts.append("code_owner_reviews_required")
        if not observed.dismiss_stale_reviews:
            drifts.append("stale_reviews_not_dismissed")
        if not observed.enforce_admins:
            drifts.append("admin_enforcement_disabled")
        if not observed.require_linear_history:
            drifts.append("linear_history_disabled")
        if not observed.require_conversation_resolution:
            drifts.append("conversation_resolution_disabled")
    return ProtectionDriftDecision(
        decision_id=github_identifier(
            "GHDRF", observed.repository_slug, observed.branch, ",".join(drifts) or "aligned"
        ),
        repository_slug=observed.repository_slug,
        branch=observed.branch,
        aligned=not drifts,
        drifts=tuple(sorted(drifts)),
        observed=observed.model_dump(mode="json"),
        expected=expected,
    )
