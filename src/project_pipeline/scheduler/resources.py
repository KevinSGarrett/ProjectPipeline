from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime

from project_pipeline.domain.scheduler import (
    ResourceClaim,
    ResourceLease,
    ResourcePool,
    ResourceRegistrySnapshot,
)


class ResourceAdmissionError(ValueError):
    """Raised when a resource claim cannot be safely admitted."""


def active_leases(registry: ResourceRegistrySnapshot, when: datetime) -> tuple[ResourceLease, ...]:
    when = when.astimezone(UTC)
    return tuple(lease for lease in registry.active_leases if lease.active_at(when))


def capacity_usage(registry: ResourceRegistrySnapshot, when: datetime) -> dict[str, int]:
    usage: dict[str, int] = defaultdict(int)
    for lease in active_leases(registry, when):
        usage[lease.claim.resource_key] += lease.claim.quantity
    return dict(usage)


def admission_reasons(
    claims: Iterable[ResourceClaim],
    registry: ResourceRegistrySnapshot,
    *,
    when: datetime,
    additional_usage: dict[str, int] | None = None,
) -> tuple[str, ...]:
    pools = {pool.resource_key: pool for pool in registry.pools}
    leases = active_leases(registry, when)
    usage = capacity_usage(registry, when)
    if additional_usage:
        for key, value in additional_usage.items():
            usage[key] = usage.get(key, 0) + value

    reasons: set[str] = set()
    for claim in claims:
        pool = pools.get(claim.resource_key)
        if pool is not None:
            available = pool.allocatable_units - usage.get(claim.resource_key, 0)
            if claim.quantity > available:
                reasons.add(f"capacity:{claim.resource_key}:{claim.quantity}>{max(0, available)}")
            continue
        for lease in leases:
            if claim.conflicts_with(lease.claim):
                reasons.add(f"lease:{claim.resource_key}:held_by:{lease.holder_id}")
    return tuple(sorted(reasons))


def add_claim_usage(
    usage: dict[str, int], claims: Iterable[ResourceClaim], pools: dict[str, ResourcePool]
) -> None:
    for claim in claims:
        if claim.resource_key in pools:
            usage[claim.resource_key] = usage.get(claim.resource_key, 0) + claim.quantity
