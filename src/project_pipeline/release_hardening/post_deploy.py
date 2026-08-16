from __future__ import annotations

from typing import Literal

from pydantic import Field

from project_pipeline.domain.base import DomainModel, utc_now

CHECKS = (
    "health",
    "version",
    "migration",
    "integration",
    "security",
    "telemetry",
    "golden_journey",
)


class PostDeploymentObservation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    target_environment: str = Field(min_length=2, max_length=120)
    live_target: bool = False
    checks: dict[str, bool]
    evidence_ids: tuple[str, ...] = ()
    observed_at_utc: object = Field(default_factory=utc_now)


class PostDeploymentDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    state: Literal["PASS", "FAIL", "BLOCKED_EXTERNAL"]
    target_environment: str
    missing_or_failed_checks: tuple[str, ...]
    live_target_verified: bool
    reasons: tuple[str, ...]


def verify_post_deployment(observation: PostDeploymentObservation) -> PostDeploymentDecision:
    missing = tuple(name for name in CHECKS if observation.checks.get(name) is not True)
    if missing:
        return PostDeploymentDecision(
            state="FAIL",
            target_environment=observation.target_environment,
            missing_or_failed_checks=missing,
            live_target_verified=False,
            reasons=("required post-deployment checks are missing or failed",),
        )
    if not observation.live_target:
        return PostDeploymentDecision(
            state="BLOCKED_EXTERNAL",
            target_environment=observation.target_environment,
            missing_or_failed_checks=(),
            live_target_verified=False,
            reasons=(
                "all check contracts are present, but no live target-environment deployment was observed",
            ),
        )
    if not observation.evidence_ids:
        return PostDeploymentDecision(
            state="FAIL",
            target_environment=observation.target_environment,
            missing_or_failed_checks=(),
            live_target_verified=False,
            reasons=("live target verification requires evidence identifiers",),
        )
    return PostDeploymentDecision(
        state="PASS",
        target_environment=observation.target_environment,
        missing_or_failed_checks=(),
        live_target_verified=True,
        reasons=(
            "all required target-environment post-deployment checks passed with live evidence",
        ),
    )
