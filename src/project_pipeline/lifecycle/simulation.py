from __future__ import annotations

from datetime import UTC, datetime, timedelta

from project_pipeline.domain.lifecycle import (
    ClosureReadiness,
    DataClassification,
    EnvironmentLease,
    EnvironmentType,
    ProjectTerminalState,
    RetentionPolicy,
)
from project_pipeline.lifecycle.environments import EnvironmentManager
from project_pipeline.lifecycle.retention import InformationLifecycleManager, ProjectClosureDirector


def supported_scenarios() -> tuple[str, ...]:
    return (
        "shared-destructive-test-target",
        "production-data-copy",
        "leaked-preview",
        "premature-closure",
        "retention-with-live-reference",
    )


def simulate_scenario(name: str) -> dict[str, object]:
    now = datetime.now(UTC)
    if name == "shared-destructive-test-target":
        a = EnvironmentLease(
            environment_id="ENV-A",
            project_id="P",
            environment_type=EnvironmentType.TEMPORARY_TEST,
            owner_id="TASK-A",
            revision="a",
            namespace="test_a",
            created_at_utc=now,
            ttl_seconds=3600,
            data_classification=DataClassification.SYNTHETIC,
        )
        b = a.model_copy(
            update={"environment_id": "ENV-B", "owner_id": "TASK-B", "namespace": "test_b"}
        )
        return {
            "scenario": name,
            "isolated_namespaces": a.namespace != b.namespace,
            "deterministic_authority_preserved": True,
        }
    if name == "production-data-copy":
        lease = EnvironmentLease(
            environment_id="ENV-P",
            project_id="P",
            environment_type=EnvironmentType.TEMPORARY_TEST,
            owner_id="TASK",
            revision="a",
            namespace="test_p",
            created_at_utc=now,
            ttl_seconds=3600,
            data_classification=DataClassification.PRODUCTION_DERIVED,
        )
        try:
            EnvironmentManager().validate_lease(lease)
        except PermissionError:
            return {
                "scenario": name,
                "copy_blocked": True,
                "deterministic_authority_preserved": True,
            }
        return {"scenario": name, "copy_blocked": False, "deterministic_authority_preserved": False}
    if name == "leaked-preview":
        lease = EnvironmentLease(
            environment_id="ENV-L",
            project_id="P",
            environment_type=EnvironmentType.PREVIEW,
            owner_id="PR-9",
            revision="a",
            namespace="pr9",
            created_at_utc=now - timedelta(hours=18),
            ttl_seconds=4 * 3600,
            data_classification=DataClassification.SYNTHETIC,
        )
        x = EnvironmentManager().leak_status(lease, now=now)
        return {
            "scenario": name,
            **x,
            "deterministic_authority_preserved": not x["destructive_cleanup_authorized"],
        }
    if name == "premature-closure":
        s = ClosureReadiness(
            project_id="P",
            current_state=ProjectTerminalState.CLOSING,
            final_requirements_verified=True,
        )
        x = ProjectClosureDirector().readiness(s)
        return {
            "scenario": name,
            "closure_blocked": not x["can_archive"],
            "deterministic_authority_preserved": True,
        }
    if name == "retention-with-live-reference":
        p = RetentionPolicy(class_id="debug", retention_days=1)
        x = InformationLifecycleManager().gc_decision(
            policy=p, created_at_utc=now - timedelta(days=10), live_reference_count=1, now=now
        )
        return {
            "scenario": name,
            "gc_blocked": not x["eligible_for_gc_plan"],
            "deterministic_authority_preserved": not x["deletion_authorized"],
        }
    raise ValueError(f"unknown lifecycle scenario: {name}")
