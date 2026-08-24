from __future__ import annotations

from pathlib import Path, PurePosixPath

from project_pipeline.domain.control import ControlSnapshot, ReadinessState
from project_pipeline.domain.scheduler import (
    AccessMode,
    ResourceClaim,
    ResourceType,
    SchedulerTaskProfile,
)
from project_pipeline.jira import load_issues

_EXCLUDED_PREFIXES = (
    "plans/",
    "jira/",
    "evidence/",
    "provenance/",
    "docs/",
)


def profiles_from_repository(
    root: Path, control: ControlSnapshot
) -> tuple[SchedulerTaskProfile, ...]:
    """Derive conservative scheduler inputs from the current Jira execution contract."""
    issues = {item["local_id"]: item for item in load_issues(root)}
    waiting = {
        item.task_id
        for item in control.readiness
        if item.state
        in {
            ReadinessState.WAITING_DEPENDENCIES,
            ReadinessState.BLOCKED,
            ReadinessState.WAITING_APPROVAL,
            ReadinessState.WAITING_CONTEXT,
            ReadinessState.WAITING_RESOURCES,
            ReadinessState.WAITING_ENVIRONMENT,
        }
    }
    profiles: list[SchedulerTaskProfile] = []
    for item in control.sequence.ordered_ready_work:
        issue = issues.get(item.task_id, {})
        claims: list[ResourceClaim] = [
            ResourceClaim(
                resource_key="machine:local/cpu_slots",
                resource_type=ResourceType.CPU_SLOT,
                access_mode=AccessMode.SHARED,
                quantity=1,
                machine_id="machine:local",
                purpose="default worker CPU admission",
            ),
            ResourceClaim(
                resource_key="machine:local/process_slots",
                resource_type=ResourceType.PROCESS_SLOT,
                access_mode=AccessMode.SHARED,
                quantity=1,
                machine_id="machine:local",
                purpose="worker process admission",
            ),
        ]
        for raw in issue.get("expected_file_locations", []):
            path = str(PurePosixPath(str(raw).replace("\\", "/")))
            if path == "." or path.startswith(_EXCLUDED_PREFIXES):
                continue
            claims.append(
                ResourceClaim(
                    resource_key=path,
                    resource_type=ResourceType.PATH,
                    access_mode=AccessMode.EXCLUSIVE,
                    purpose="declared implementation path",
                )
            )
        # Common high-contention domains receive semantic leases even when a path is not explicit.
        labels = set(issue.get("labels", []))
        if "migration" in labels or any(
            "migration" in str(x).lower() for x in issue.get("scope", [])
        ):
            claims.append(
                ResourceClaim(
                    resource_key="database:migration-sequence", resource_type=ResourceType.DATABASE
                )
            )
        if "aws" in labels or "infrastructure" in labels:
            claims.append(
                ResourceClaim(
                    resource_key="environment:infrastructure",
                    resource_type=ResourceType.INFRASTRUCTURE,
                )
            )
        profiles.append(
            SchedulerTaskProfile(
                task_id=item.task_id,
                project_id=control.project_id,
                sequence_rank=item.rank,
                utility_score=max(0, item.score.total_score),
                priority=issue.get("priority", "P1"),
                critical_path=item.on_critical_path,
                claims=tuple(claims),
                owner_id=issue.get("owner_required_capability"),
                workspace_isolated=True,
                policy_eligible=True,
                productive_idle=bool(waiting) and item.task_id not in waiting,
                protected_capacity_consumption=False,
            )
        )
    return tuple(profiles)


def claims_for_task(root: Path, task_id: str) -> tuple[ResourceClaim, ...]:
    """Recover deterministic claims for one task from Jira issue metadata."""
    issues = {item["local_id"]: item for item in load_issues(root)}
    issue = issues.get(task_id)
    if issue is None:
        return ()
    claims: list[ResourceClaim] = [
        ResourceClaim(
            resource_key="machine:local/cpu_slots",
            resource_type=ResourceType.CPU_SLOT,
            access_mode=AccessMode.SHARED,
            quantity=1,
            machine_id="machine:local",
            purpose="default worker CPU admission",
        ),
        ResourceClaim(
            resource_key="machine:local/process_slots",
            resource_type=ResourceType.PROCESS_SLOT,
            access_mode=AccessMode.SHARED,
            quantity=1,
            machine_id="machine:local",
            purpose="worker process admission",
        ),
    ]
    for raw in issue.get("expected_file_locations", []):
        path = str(PurePosixPath(str(raw).replace("\\", "/")))
        if path == "." or path.startswith(_EXCLUDED_PREFIXES):
            continue
        claims.append(
            ResourceClaim(
                resource_key=path,
                resource_type=ResourceType.PATH,
                access_mode=AccessMode.EXCLUSIVE,
                purpose="declared implementation path",
            )
        )
    labels = set(issue.get("labels", []))
    if "migration" in labels or any("migration" in str(x).lower() for x in issue.get("scope", [])):
        claims.append(
            ResourceClaim(
                resource_key="database:migration-sequence", resource_type=ResourceType.DATABASE
            )
        )
    if "aws" in labels or "infrastructure" in labels:
        claims.append(
            ResourceClaim(
                resource_key="environment:infrastructure",
                resource_type=ResourceType.INFRASTRUCTURE,
            )
        )
    deduped: list[ResourceClaim] = []
    seen: set[tuple[str, str, str, int]] = set()
    for claim in claims:
        key = (
            claim.resource_type.value,
            claim.resource_key,
            claim.access_mode.value,
            claim.quantity,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)
    return tuple(deduped)
