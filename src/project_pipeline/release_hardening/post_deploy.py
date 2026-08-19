from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.io import iter_repository_files

_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template"})


def _is_committed_env(relative: str) -> bool:
    name = Path(relative).name
    return name == ".env" or (name.startswith(".env.") and name not in _ENV_TEMPLATES)


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


def execute_local_post_deployment(
    root: Path,
    *,
    target_environment: str,
    live_target: bool = False,
    evidence_ids: tuple[str, ...] = (),
) -> tuple[PostDeploymentObservation, PostDeploymentDecision]:
    """Run the post-deployment checks against a real local installation root."""

    root = root.resolve()
    identity = (
        (root / "config/project.json").is_file()
        and (root / "plans/PLAN_CATALOG.json").is_file()
        and (root / "jira/BOARD_MANIFEST.json").is_file()
    )
    version_ok = False
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get(
            "project", {}
        )
        version_ok = bool(str(project.get("version") or "").strip())
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        version_ok = False
    migrations_ok = False
    try:
        catalog = json.loads((root / "database/MIGRATION_CATALOG.json").read_text(encoding="utf-8"))
        migrations_ok = bool(catalog.get("migrations"))
    except (OSError, json.JSONDecodeError, TypeError):
        migrations_ok = False
    committed_env = any(
        _is_committed_env(path.relative_to(root).as_posix()) for path in iter_repository_files(root)
    )
    health_ok = False
    telemetry_ok = False
    try:
        from project_pipeline.configuration import load_runtime_configuration
        from project_pipeline.runtime.bootstrap import run_bootstrap

        configuration = load_runtime_configuration(root, environment={})
        report = run_bootstrap(root, configuration, prepare=False, validate_repository=False)
        health_ok = all(item.status == "PASS" for item in report.checks if item.required)
        telemetry_ok = configuration.settings.telemetry is not None
    except Exception:
        health_ok = False
        telemetry_ok = False
    golden_ok = (root / "tests/test_verification_golden.py").is_file()
    observation = PostDeploymentObservation(
        target_environment=target_environment,
        live_target=live_target,
        checks={
            "health": health_ok,
            "version": version_ok,
            "migration": migrations_ok,
            "integration": identity,
            "security": not committed_env,
            "telemetry": telemetry_ok,
            "golden_journey": golden_ok,
        },
        evidence_ids=evidence_ids,
    )
    return observation, verify_post_deployment(observation)
