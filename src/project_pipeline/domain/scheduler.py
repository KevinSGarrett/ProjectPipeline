from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.domain.identifiers import IdentifierKind, validate_identifier

SCHEDULER_ID = re.compile(r"^(SCHED|LANE|LEASE|SIM)-[A-F0-9]{20}$")


def scheduler_identifier(prefix: Literal["SCHED", "LANE", "LEASE", "SIM"], *parts: str) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("scheduler identifier parts must be non-empty")
    canonical = "\x1f".join(str(part).strip() for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20].upper()
    return f"{prefix}-{digest}"


def semantic_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResourceType(StrEnum):
    PATH = "PATH"
    SYMBOL = "SYMBOL"
    MODULE = "MODULE"
    DATABASE = "DATABASE"
    SCHEMA = "SCHEMA"
    API_CONTRACT = "API_CONTRACT"
    CONFIGURATION = "CONFIGURATION"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    DOCKER = "DOCKER"
    ENVIRONMENT = "ENVIRONMENT"
    RELEASE = "RELEASE"
    FIXTURE = "FIXTURE"
    SERVICE = "SERVICE"
    PORT = "PORT"
    GPU = "GPU"
    GPU_MEMORY_MB = "GPU_MEMORY_MB"
    CPU_SLOT = "CPU_SLOT"
    MEMORY_MB = "MEMORY_MB"
    DISK_MB = "DISK_MB"
    NETWORK_SLOT = "NETWORK_SLOT"
    PROCESS_SLOT = "PROCESS_SLOT"
    CONCURRENCY_SLOT = "CONCURRENCY_SLOT"
    PROVIDER_SLOT = "PROVIDER_SLOT"
    REVIEW_SLOT = "REVIEW_SLOT"


class AccessMode(StrEnum):
    SHARED = "SHARED"
    EXCLUSIVE = "EXCLUSIVE"


class BackpressureMode(StrEnum):
    NORMAL = "NORMAL"
    CONGESTED = "CONGESTED"
    BROWNOUT = "BROWNOUT"
    HALT_NEW_WORK = "HALT_NEW_WORK"


class AdmissionState(StrEnum):
    ADMITTED = "ADMITTED"
    CONFLICT = "CONFLICT"
    CAPACITY_EXHAUSTED = "CAPACITY_EXHAUSTED"
    LEASE_UNAVAILABLE = "LEASE_UNAVAILABLE"
    BACKPRESSURE = "BACKPRESSURE"
    POLICY_DENIED = "POLICY_DENIED"
    WORKSPACE_UNSAFE = "WORKSPACE_UNSAFE"


class ResourceClaim(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    resource_key: str = Field(min_length=1, max_length=512)
    resource_type: ResourceType
    access_mode: AccessMode = AccessMode.EXCLUSIVE
    quantity: int = Field(default=1, ge=1, le=10_000_000)
    machine_id: str | None = Field(default=None, max_length=191)
    purpose: str | None = Field(default=None, max_length=1000)

    @field_validator("resource_key")
    @classmethod
    def normalize_resource_key(cls, value: str) -> str:
        value = value.strip().replace("\\", "/")
        if not value or "\x00" in value:
            raise ValueError("resource key must be non-empty and contain no NUL bytes")
        if value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
            raise ValueError(
                "resource keys must be logical or repository-relative, not absolute paths"
            )
        if any(part == ".." for part in value.split("/")):
            raise ValueError("resource keys cannot escape their logical root")
        return re.sub(r"/+", "/", value).rstrip("/") or "."

    def conflicts_with(self, other: ResourceClaim) -> bool:
        if self.resource_type is ResourceType.PATH and other.resource_type is ResourceType.PATH:
            left, right = self.resource_key, other.resource_key
            overlaps = left == right or left.startswith(right + "/") or right.startswith(left + "/")
        else:
            overlaps = self.resource_key == other.resource_key
        return overlaps and (
            self.access_mode is AccessMode.EXCLUSIVE or other.access_mode is AccessMode.EXCLUSIVE
        )


class SchedulerTaskProfile(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    project_id: str
    sequence_rank: int = Field(ge=1)
    utility_score: int = Field(ge=0)
    priority: str = Field(pattern=r"^P[0-3]$")
    critical_path: bool = False
    claims: tuple[ResourceClaim, ...] = ()
    owner_id: str | None = Field(default=None, max_length=191)
    workspace_isolated: bool = True
    policy_eligible: bool = True
    productive_idle: bool = False
    protected_capacity_consumption: bool = False

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @model_validator(mode="after")
    def validate_claims(self) -> SchedulerTaskProfile:
        identities = [
            (claim.resource_type.value, claim.resource_key, claim.access_mode.value)
            for claim in self.claims
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("scheduler task profile contains duplicate resource claims")
        return self


class ResourcePool(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    resource_key: str = Field(min_length=1, max_length=512)
    resource_type: ResourceType
    capacity_units: int = Field(ge=1)
    reserved_units: int = Field(default=0, ge=0)
    machine_id: str | None = Field(default=None, max_length=191)
    observed: bool = False

    @model_validator(mode="after")
    def validate_reserve(self) -> ResourcePool:
        if self.reserved_units >= self.capacity_units:
            raise ValueError("resource reserve must leave at least one allocatable unit")
        return self

    @property
    def allocatable_units(self) -> int:
        return self.capacity_units - self.reserved_units


class ResourceLease(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    lease_id: str
    task_id: str
    holder_id: str = Field(min_length=1, max_length=191)
    claim: ResourceClaim
    fencing_token: int = Field(ge=1)
    acquired_at_utc: datetime = Field(default_factory=utc_now)
    expires_at_utc: datetime
    renewed_at_utc: datetime | None = None
    released_at_utc: datetime | None = None

    @field_validator("lease_id")
    @classmethod
    def validate_lease_id(cls, value: str) -> str:
        if not SCHEDULER_ID.fullmatch(value) or not value.startswith("LEASE-"):
            raise ValueError(f"invalid resource lease identifier: {value}")
        return value

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @field_validator("acquired_at_utc", "expires_at_utc", "renewed_at_utc", "released_at_utc")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("lease timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ResourceLease:
        if self.expires_at_utc <= self.acquired_at_utc:
            raise ValueError("lease expiry must be later than acquisition")
        if self.renewed_at_utc and self.renewed_at_utc < self.acquired_at_utc:
            raise ValueError("lease renewal cannot precede acquisition")
        if self.released_at_utc and self.released_at_utc < self.acquired_at_utc:
            raise ValueError("lease release cannot precede acquisition")
        return self

    def active_at(self, when: datetime) -> bool:
        when = when.astimezone(UTC)
        return self.released_at_utc is None and self.expires_at_utc > when


class ResourceRegistrySnapshot(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    registry_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    pools: tuple[ResourcePool, ...]
    active_leases: tuple[ResourceLease, ...] = ()
    observed_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("observed_at_utc")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("registry timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_unique_pools(self) -> ResourceRegistrySnapshot:
        keys = [pool.resource_key for pool in self.pools]
        if len(keys) != len(set(keys)):
            raise ValueError("resource registry contains duplicate pool keys")
        return self

    @classmethod
    def create(
        cls,
        *,
        pools: Iterable[ResourcePool],
        active_leases: Iterable[ResourceLease] = (),
        observed_at_utc: datetime | None = None,
    ) -> ResourceRegistrySnapshot:
        pool_tuple = tuple(sorted(pools, key=lambda item: item.resource_key))
        lease_tuple = tuple(sorted(active_leases, key=lambda item: item.lease_id))
        payload = {
            "pools": [item.model_dump(mode="json") for item in pool_tuple],
            "active_leases": [item.model_dump(mode="json") for item in lease_tuple],
        }
        return cls(
            registry_id=semantic_fingerprint(payload),
            pools=pool_tuple,
            active_leases=lease_tuple,
            observed_at_utc=observed_at_utc or utc_now(),
        )


class BackpressureSignals(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    queue_depth: int = Field(default=0, ge=0)
    scheduler_queue_lag_seconds: float = Field(default=0, ge=0)
    memory_used_percent: float | None = Field(default=None, ge=0, le=100)
    disk_free_percent: float | None = Field(default=None, ge=0, le=100)
    outbox_depth: int = Field(default=0, ge=0)
    verification_queue_depth: int = Field(default=0, ge=0)
    retry_storm_count: int = Field(default=0, ge=0)


class BackpressurePolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    congested_queue_depth: int = Field(default=50, ge=1)
    brownout_queue_depth: int = Field(default=200, ge=1)
    halt_queue_depth: int = Field(default=1000, ge=1)
    congested_lag_seconds: float = Field(default=30, ge=0)
    brownout_lag_seconds: float = Field(default=120, ge=0)
    memory_brownout_percent: float = Field(default=90, ge=1, le=100)
    memory_halt_percent: float = Field(default=97, ge=1, le=100)
    disk_brownout_free_percent: float = Field(default=10, ge=0, le=100)
    disk_halt_free_percent: float = Field(default=3, ge=0, le=100)
    retry_storm_brownout_count: int = Field(default=8, ge=1)
    congested_lane_fraction: float = Field(default=0.5, gt=0, le=1)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> BackpressurePolicy:
        if not (self.congested_queue_depth < self.brownout_queue_depth < self.halt_queue_depth):
            raise ValueError("queue backpressure thresholds must be strictly increasing")
        if self.memory_brownout_percent >= self.memory_halt_percent:
            raise ValueError("memory brownout threshold must be below halt threshold")
        if self.disk_halt_free_percent >= self.disk_brownout_free_percent:
            raise ValueError("disk halt threshold must be below brownout free-space threshold")
        return self


class BackpressureDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    mode: BackpressureMode
    lane_fraction: float = Field(ge=0, le=1)
    admit_new_work: bool
    reasons: tuple[str, ...] = ()


class ConflictEdge(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    left_task_id: str
    right_task_id: str
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_edge(self) -> ConflictEdge:
        validate_identifier(self.left_task_id, IdentifierKind.ISSUE)
        validate_identifier(self.right_task_id, IdentifierKind.ISSUE)
        if self.left_task_id >= self.right_task_id:
            raise ValueError("conflict edges must use stable ascending task ordering")
        if not self.reasons:
            raise ValueError("conflict edges require at least one reason")
        return self


class AdmissionDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    state: AdmissionState
    admitted: bool
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_decision(self) -> AdmissionDecision:
        validate_identifier(self.task_id, IdentifierKind.ISSUE)
        if self.admitted != (self.state is AdmissionState.ADMITTED):
            raise ValueError("admission boolean must agree with admission state")
        if not self.admitted and not self.reasons:
            raise ValueError("rejected admission requires at least one reason")
        return self


class LaneAssignment(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    lane_id: str
    task_id: str
    rank: int = Field(ge=1)
    utility_score: int = Field(ge=0)
    claims: tuple[ResourceClaim, ...] = ()

    @field_validator("lane_id")
    @classmethod
    def validate_lane_id(cls, value: str) -> str:
        if not SCHEDULER_ID.fullmatch(value) or not value.startswith("LANE-"):
            raise ValueError(f"invalid lane identifier: {value}")
        return value

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)


class SchedulerPlan(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    plan_id: str
    project_id: str
    control_snapshot_id: str
    registry_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    backpressure: BackpressureDecision
    selection_method: Literal["EXACT_BOUNDED", "DETERMINISTIC_GREEDY", "ORTOOLS_CP_SAT"]
    candidate_count: int = Field(ge=0)
    lane_limit: int = Field(ge=0)
    lanes: tuple[LaneAssignment, ...]
    conflicts: tuple[ConflictEdge, ...]
    admissions: tuple[AdmissionDecision, ...]
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        if not SCHEDULER_ID.fullmatch(value) or not value.startswith("SCHED-"):
            raise ValueError(f"invalid scheduler plan identifier: {value}")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @field_validator("generated_at_utc")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduler plan timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_plan(self) -> SchedulerPlan:
        selected = [lane.task_id for lane in self.lanes]
        if len(selected) != len(set(selected)):
            raise ValueError("scheduler plan cannot select a task more than once")
        if len(self.lanes) > self.lane_limit:
            raise ValueError("scheduler plan exceeds lane limit")
        return self


class LeaseBundle(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    holder_id: str
    leases: tuple[ResourceLease, ...]
    acquired: bool
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_bundle(self) -> LeaseBundle:
        validate_identifier(self.task_id, IdentifierKind.ISSUE)
        if self.acquired and not self.leases:
            raise ValueError("acquired lease bundle must contain leases")
        if not self.acquired and not self.reasons:
            raise ValueError("failed lease bundle must include reasons")
        return self


class SchedulerSimulationResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    simulation_id: str
    scenario_name: str = Field(min_length=1, max_length=191)
    plan: SchedulerPlan
    expected_lane_count: int | None = Field(default=None, ge=0)
    assertions_passed: bool
    findings: tuple[str, ...] = ()

    @field_validator("simulation_id")
    @classmethod
    def validate_simulation_id(cls, value: str) -> str:
        if not SCHEDULER_ID.fullmatch(value) or not value.startswith("SIM-"):
            raise ValueError(f"invalid scheduler simulation identifier: {value}")
        return value


def local_resource_pools(root: Path) -> tuple[ResourcePool, ...]:
    """Observe portable local CPU/memory/disk capacity without inventing GPU facts."""
    cpu = max(1, os.cpu_count() or 1)
    # Keep deterministic control-plane reserve and avoid claiming all host capacity for workers.
    cpu_capacity = max(2, cpu)
    cpu_reserve = 1 if cpu_capacity > 1 else 0

    memory_mb: int | None = None
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                memory_mb = max(1, int(status.ullTotalPhys // (1024 * 1024)))
        elif hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if (
                isinstance(pages, int)
                and isinstance(page_size, int)
                and pages > 0
                and page_size > 0
            ):
                memory_mb = max(1, int(pages * page_size // (1024 * 1024)))
    except (OSError, ValueError, AttributeError):
        memory_mb = None

    disk = shutil.disk_usage(root)
    disk_mb = max(1, int(disk.free // (1024 * 1024)))

    pools = [
        ResourcePool(
            resource_key="machine:local/cpu_slots",
            resource_type=ResourceType.CPU_SLOT,
            capacity_units=cpu_capacity,
            reserved_units=cpu_reserve,
            machine_id="machine:local",
            observed=True,
        ),
        ResourcePool(
            resource_key="machine:local/process_slots",
            resource_type=ResourceType.PROCESS_SLOT,
            capacity_units=max(2, min(64, cpu_capacity * 2)),
            reserved_units=1,
            machine_id="machine:local",
            observed=True,
        ),
        ResourcePool(
            resource_key="machine:local/disk_mb",
            resource_type=ResourceType.DISK_MB,
            capacity_units=disk_mb,
            reserved_units=max(1, min(disk_mb - 1, int(disk_mb * 0.05))) if disk_mb > 1 else 0,
            machine_id="machine:local",
            observed=True,
        ),
    ]
    if memory_mb and memory_mb > 1:
        pools.append(
            ResourcePool(
                resource_key="machine:local/memory_mb",
                resource_type=ResourceType.MEMORY_MB,
                capacity_units=memory_mb,
                reserved_units=max(1, min(memory_mb - 1, int(memory_mb * 0.15))),
                machine_id="machine:local",
                observed=True,
            )
        )
    return tuple(pools)


def lease_expiry(now: datetime, ttl_seconds: int) -> datetime:
    if ttl_seconds <= 0:
        raise ValueError("lease TTL must be positive")
    return now.astimezone(UTC) + timedelta(seconds=ttl_seconds)
