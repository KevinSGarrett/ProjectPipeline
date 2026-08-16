from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from project_pipeline.domain.scheduler import (
    AccessMode,
    ResourceClaim,
    ResourceLease,
    ResourcePool,
    ResourceType,
    scheduler_identifier,
)


def test_scheduler_identifier_is_deterministic() -> None:
    assert scheduler_identifier("SCHED", "a", "b") == scheduler_identifier("SCHED", "a", "b")
    assert scheduler_identifier("LANE", "a", "b").startswith("LANE-")


def test_resource_claim_rejects_absolute_or_escape_path() -> None:
    with pytest.raises(ValidationError):
        ResourceClaim(resource_key="/etc/passwd", resource_type=ResourceType.PATH)
    with pytest.raises(ValidationError):
        ResourceClaim(resource_key="src/../secret", resource_type=ResourceType.PATH)


def test_path_conflict_detects_ancestor_scope() -> None:
    parent = ResourceClaim(resource_key="src/auth", resource_type=ResourceType.PATH)
    child = ResourceClaim(resource_key="src/auth/token.py", resource_type=ResourceType.PATH)
    other = ResourceClaim(resource_key="src/billing", resource_type=ResourceType.PATH)
    assert parent.conflicts_with(child)
    assert not parent.conflicts_with(other)


def test_shared_claims_do_not_conflict_but_exclusive_does() -> None:
    left = ResourceClaim(
        resource_key="machine:local/cpu_slots",
        resource_type=ResourceType.CPU_SLOT,
        access_mode=AccessMode.SHARED,
    )
    right = ResourceClaim(
        resource_key="machine:local/cpu_slots",
        resource_type=ResourceType.CPU_SLOT,
        access_mode=AccessMode.SHARED,
    )
    exclusive = ResourceClaim(
        resource_key="machine:local/cpu_slots", resource_type=ResourceType.CPU_SLOT
    )
    assert not left.conflicts_with(right)
    assert left.conflicts_with(exclusive)


def test_resource_pool_reserve_cannot_consume_entire_pool() -> None:
    with pytest.raises(ValidationError):
        ResourcePool(
            resource_key="cpu",
            resource_type=ResourceType.CPU_SLOT,
            capacity_units=4,
            reserved_units=4,
        )


def test_resource_lease_requires_future_expiry() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ResourceLease(
            lease_id=scheduler_identifier("LEASE", "x"),
            task_id="PP-TASK-000001",
            holder_id="worker:1",
            claim=ResourceClaim(resource_key="src/auth", resource_type=ResourceType.PATH),
            fencing_token=1,
            acquired_at_utc=now,
            expires_at_utc=now - timedelta(seconds=1),
        )
