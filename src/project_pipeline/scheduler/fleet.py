"""Fleet placement, eligibility, and host-profile admission."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import Field

from project_pipeline.domain.base import DomainModel
from project_pipeline.domain.scheduler import (
    AccessMode,
    ResourceClaim,
    ResourceLease,
    ResourcePool,
    ResourceType,
    SchedulerTaskProfile,
)

LEGACY_CUDA_COMPUTE_CAPABILITY = 2.0
MODERN_CUDA_MIN_COMPUTE_CAPABILITY = 5.0
HostState = Literal["READY", "STALE", "OFFLINE", "DRAINED", "QUARANTINED", "ENROLLMENT_PENDING"]


class MachineProfile(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    machine_id: str
    hostname: str
    role: str
    state: HostState = "READY"
    observed_at_utc: datetime
    ttl_seconds: int = Field(default=300, ge=1)
    os_family: str = "windows"
    isa_flags: tuple[str, ...] = ()
    cuda_compute_capability: float | None = None
    gpu_name: str | None = None
    cpu_slots: int = Field(ge=1)
    memory_mb: int = Field(ge=1)
    disk_mb: int = Field(ge=1)
    principal: str = "worker"
    modern_cuda_eligible: bool = False

    def fresh_at(self, when: datetime) -> bool:
        when = when.astimezone(UTC)
        return when - self.observed_at_utc <= timedelta(seconds=self.ttl_seconds)

    def eligibility_reasons(
        self,
        *,
        when: datetime,
        require_avx2: bool = False,
        require_modern_cuda: bool = False,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.state in {"STALE", "OFFLINE", "DRAINED", "QUARANTINED", "ENROLLMENT_PENDING"}:
            reasons.append(f"host_state:{self.state}")
        if not self.fresh_at(when):
            reasons.append("stale_capacity")
        if require_avx2 and "avx2" not in {item.lower() for item in self.isa_flags}:
            reasons.append("unsupported_isa:avx2")
        if require_modern_cuda:
            capability = self.cuda_compute_capability
            if (
                not self.modern_cuda_eligible
                or capability is None
                or capability < MODERN_CUDA_MIN_COMPUTE_CAPABILITY
            ):
                reasons.append("unsupported_gpu:modern_cuda")
        return tuple(reasons)

    def physical_pools(self) -> tuple[ResourcePool, ...]:
        reserve_cpu = 1 if self.cpu_slots > 1 else 0
        return (
            ResourcePool(
                resource_key=f"{self.machine_id}/cpu_slots",
                resource_type=ResourceType.CPU_SLOT,
                capacity_units=self.cpu_slots,
                reserved_units=reserve_cpu,
                machine_id=self.machine_id,
                observed=True,
            ),
            ResourcePool(
                resource_key=f"{self.machine_id}/memory_mb",
                resource_type=ResourceType.MEMORY_MB,
                capacity_units=self.memory_mb,
                reserved_units=max(1, min(self.memory_mb - 1, int(self.memory_mb * 0.15))),
                machine_id=self.machine_id,
                observed=True,
            ),
            ResourcePool(
                resource_key=f"{self.machine_id}/disk_mb",
                resource_type=ResourceType.DISK_MB,
                capacity_units=self.disk_mb,
                reserved_units=max(1, min(self.disk_mb - 1, int(self.disk_mb * 0.05))),
                machine_id=self.machine_id,
                observed=True,
            ),
            ResourcePool(
                resource_key=f"{self.machine_id}/process_slots",
                resource_type=ResourceType.PROCESS_SLOT,
                capacity_units=max(2, self.cpu_slots),
                reserved_units=1,
                machine_id=self.machine_id,
                observed=True,
            ),
        )


def physical_claims_for_machine(
    machine_id: str,
    *,
    cpu: int = 1,
    memory_mb: int = 256,
    disk_mb: int = 256,
    processes: int = 1,
) -> tuple[ResourceClaim, ...]:
    return (
        ResourceClaim(
            resource_key=f"{machine_id}/cpu_slots",
            resource_type=ResourceType.CPU_SLOT,
            access_mode=AccessMode.SHARED,
            quantity=cpu,
            machine_id=machine_id,
            purpose="machine-qualified CPU",
        ),
        ResourceClaim(
            resource_key=f"{machine_id}/memory_mb",
            resource_type=ResourceType.MEMORY_MB,
            access_mode=AccessMode.SHARED,
            quantity=memory_mb,
            machine_id=machine_id,
            purpose="machine-qualified RAM",
        ),
        ResourceClaim(
            resource_key=f"{machine_id}/disk_mb",
            resource_type=ResourceType.DISK_MB,
            access_mode=AccessMode.SHARED,
            quantity=disk_mb,
            machine_id=machine_id,
            purpose="machine-qualified disk",
        ),
        ResourceClaim(
            resource_key=f"{machine_id}/process_slots",
            resource_type=ResourceType.PROCESS_SLOT,
            access_mode=AccessMode.SHARED,
            quantity=processes,
            machine_id=machine_id,
            purpose="machine-qualified process",
        ),
    )


def select_target(
    profiles: tuple[MachineProfile, ...],
    *,
    when: datetime,
    require_modern_cuda: bool = False,
    require_avx2: bool = False,
    prefer_roles: tuple[str, ...] = ("CPU_WORKER", "MEMORY_HEAVY_BATCH_WORKER"),
) -> tuple[MachineProfile | None, tuple[str, ...]]:
    """Deterministic placement: eligibility first, then remaining disk, then machine_id."""

    eligible: list[MachineProfile] = []
    denials: list[str] = []
    for profile in sorted(profiles, key=lambda item: item.machine_id):
        reasons = list(
            profile.eligibility_reasons(
                when=when, require_avx2=require_avx2, require_modern_cuda=require_modern_cuda
            )
        )
        if reasons:
            denials.append(f"{profile.machine_id}:{'|'.join(reasons)}")
            continue
        if profile.role not in prefer_roles and profile.role != "PRIMARY_CONTROL_CANDIDATE":
            denials.append(f"{profile.machine_id}:role:{profile.role}")
            continue
        eligible.append(profile)
    if not eligible:
        return None, tuple(denials)
    workers = [item for item in eligible if item.role != "PRIMARY_CONTROL_CANDIDATE"]
    pool = workers or eligible
    chosen = sorted(pool, key=lambda item: (-item.disk_mb, item.machine_id))[0]
    return chosen, tuple(denials)


def bind_profile_claims(profile: SchedulerTaskProfile, machine_id: str) -> SchedulerTaskProfile:
    rewritten: list[ResourceClaim] = []
    for claim in profile.claims:
        if claim.machine_id in {None, "machine:local"} and claim.resource_type in {
            ResourceType.CPU_SLOT,
            ResourceType.MEMORY_MB,
            ResourceType.DISK_MB,
            ResourceType.PROCESS_SLOT,
            ResourceType.GPU,
            ResourceType.GPU_MEMORY_MB,
        }:
            key = claim.resource_key.replace("machine:local", machine_id)
            rewritten.append(
                claim.model_copy(update={"resource_key": key, "machine_id": machine_id})
            )
        else:
            rewritten.append(claim)
    return profile.model_copy(update={"claims": tuple(rewritten)})


def drain_host(profile: MachineProfile) -> MachineProfile:
    return profile.model_copy(update={"state": "DRAINED"})


def resume_host(profile: MachineProfile, *, when: datetime | None = None) -> MachineProfile:
    """Restore READY without treating resume as a freshness observation."""

    return profile.model_copy(update={"state": "READY"})


def _join_ids(values: Iterable[str]) -> str:
    return ",".join(sorted(values))


def _token_set(*values: object) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for item in str(value or "").split(","):
            if item and item != "none":
                tokens.add(item)
    return tokens


def occupancy_from_leases(leases: Iterable[ResourceLease]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[ResourceLease]] = {}
    for lease in leases:
        machine_id = lease.claim.machine_id
        if not machine_id:
            continue
        grouped.setdefault(machine_id, []).append(lease)
    occupancy: dict[str, dict[str, Any]] = {}
    for machine_id, items in grouped.items():
        tasks = {item.task_id for item in items}
        lease_ids = {item.lease_id for item in items}
        fences = {str(item.fencing_token) for item in items}
        occupancy[machine_id] = {
            "active_jobs": len(tasks),
            "lease_id": _join_ids(lease_ids),
            "assignment": _join_ids(tasks),
            "fence": _join_ids(fences),
        }
    return occupancy


def occupancy_from_jobs(
    jobs: Iterable[Mapping[str, Any]], *, when: datetime
) -> dict[str, dict[str, Any]]:
    when = when.astimezone(UTC)
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for job in jobs:
        host_id = str(job.get("host_id") or "")
        outcome = str(job.get("outcome") or "")
        if not host_id or outcome not in {"ACCEPTED", "EXECUTED"}:
            continue
        deadline_raw = job.get("deadline_utc")
        if deadline_raw:
            deadline = datetime.fromisoformat(str(deadline_raw).replace("Z", "+00:00"))
            if deadline.astimezone(UTC) <= when:
                continue
        grouped.setdefault(host_id, []).append(job)
    occupancy: dict[str, dict[str, Any]] = {}
    for machine_id, items in grouped.items():
        job_ids = {str(item.get("job_id") or item.get("assignment") or "") for item in items}
        job_ids.discard("")
        lease_ids = {str(item.get("lease_id") or "") for item in items}
        lease_ids.discard("")
        fences = {str(item.get("fence") or "") for item in items}
        fences.discard("")
        occupancy[machine_id] = {
            "active_jobs": len(job_ids) or len(items),
            "lease_id": _join_ids(lease_ids) if lease_ids else "none",
            "assignment": _join_ids(job_ids) if job_ids else "none",
            "fence": _join_ids(fences) if fences else "none",
        }
    return occupancy


def merge_occupancy(
    *sources: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for source in sources:
        for machine_id, row in source.items():
            existing = merged.get(machine_id)
            if existing is None:
                merged[machine_id] = dict(row)
                continue
            jobs = max(int(existing.get("active_jobs") or 0), int(row.get("active_jobs") or 0))
            lease_ids = _token_set(existing.get("lease_id"), row.get("lease_id"))
            assignments = _token_set(existing.get("assignment"), row.get("assignment"))
            fences = _token_set(existing.get("fence"), row.get("fence"))
            merged[machine_id] = {
                "active_jobs": jobs,
                "lease_id": _join_ids(lease_ids) if lease_ids else "none",
                "assignment": _join_ids(assignments) if assignments else "none",
                "fence": _join_ids(fences) if fences else "none",
            }
    return merged


def fleet_projection(
    profiles: tuple[MachineProfile, ...],
    *,
    when: datetime,
    occupancy: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    known = occupancy is not None
    occupancy = occupancy or {}
    for profile in profiles:
        reasons = profile.eligibility_reasons(when=when)
        freshness = "fresh" if profile.fresh_at(when) else "stale"
        bound = occupancy.get(profile.machine_id)
        if bound is not None:
            active_jobs: int | str = int(bound.get("active_jobs") or 0)
            lease_id = str(bound.get("lease_id") or "none")
            assignment = str(bound.get("assignment") or "none")
            fence = str(bound.get("fence") or "none")
        elif known:
            active_jobs = 0
            lease_id = "none"
            assignment = "none"
            fence = "none"
        else:
            active_jobs = "unknown"
            lease_id = "unknown"
            assignment = "unknown"
            fence = "unknown"
        rows.append(
            {
                "machine_id": profile.machine_id,
                "hostname": profile.hostname,
                "role": profile.role,
                "state": profile.state if profile.fresh_at(when) else "STALE",
                "freshness": freshness,
                "eligibility": "eligible" if not reasons else "denied",
                "denial_reasons": reasons,
                "cpu_slots": profile.cpu_slots,
                "memory_mb": profile.memory_mb,
                "disk_mb": profile.disk_mb,
                "gpu_name": profile.gpu_name,
                "cuda_compute_capability": profile.cuda_compute_capability,
                "principal": profile.principal,
                "observed_at_utc": profile.observed_at_utc.isoformat(),
                "active_jobs": active_jobs,
                "lease_id": lease_id,
                "assignment": assignment,
                "fence": fence,
            }
        )
    return rows
