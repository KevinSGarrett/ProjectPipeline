from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now

RESILIENCE_ID = re.compile(
    r"^(INCIDENT|FAILOVER|MODE|RPO|BACKUP|RESTORE|RUNTIME|RECOVERY)-[A-F0-9]{20}$"
)


def resilience_identifier(prefix: str, *parts: str) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("resilience identifier parts must be non-empty")
    payload = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def resilience_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class FailureDomain(StrEnum):
    PROVIDER = "PROVIDER"
    API = "API"
    MACHINE = "MACHINE"
    NETWORK = "NETWORK"
    DATABASE = "DATABASE"
    EXTERNAL_SYSTEM = "EXTERNAL_SYSTEM"
    QUOTA = "QUOTA"
    BUDGET = "BUDGET"
    GPU = "GPU"
    CLOUD = "CLOUD"


class OperatingMode(StrEnum):
    FULL = "FULL"
    DEGRADED = "DEGRADED"
    LOCAL_FIRST = "LOCAL_FIRST"
    RECOVERY = "RECOVERY"
    PAUSED = "PAUSED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class MachineRole(StrEnum):
    PRIMARY_CONTROL = "PRIMARY_CONTROL"
    STANDBY_CONTROL = "STANDBY_CONTROL"
    GPU_WORKER = "GPU_WORKER"
    CPU_WORKER = "CPU_WORKER"
    RECOVERY = "RECOVERY"
    CLOUD_BURST = "CLOUD_BURST"


class RuntimeKind(StrEnum):
    LLAMA_CPP = "LLAMA_CPP"
    OLLAMA = "OLLAMA"
    LLAMA_SWAP = "LLAMA_SWAP"


class BackupTool(StrEnum):
    PGBACKREST = "PGBACKREST"
    RESTIC = "RESTIC"


class RestoreState(StrEnum):
    NOT_VERIFIED = "NOT_VERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class RecoveryObjective(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    objective_id: str
    domain: str = Field(min_length=2, max_length=100)
    rpo_seconds: int = Field(ge=0)
    rto_seconds: int = Field(gt=0)
    backup_strategy: str = Field(min_length=3, max_length=1000)
    destructive_restore_interval_days: int = Field(gt=0, le=365)
    rationale: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def validate_identifier(self) -> RecoveryObjective:
        if not RESILIENCE_ID.fullmatch(self.objective_id) or not self.objective_id.startswith(
            "RPO-"
        ):
            raise ValueError("invalid recovery objective id")
        return self


class MachineHealth(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    machine_id: str = Field(min_length=2, max_length=200)
    roles: tuple[MachineRole, ...]
    healthy: bool
    heartbeat_at_utc: datetime
    capabilities: tuple[str, ...] = ()
    environment: str = "local"
    capacity: dict[str, float] = Field(default_factory=dict)
    active_lease_id: str | None = None
    fencing_token: int = Field(ge=0, default=0)

    @field_validator("heartbeat_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_roles(self) -> MachineHealth:
        if not self.roles:
            raise ValueError("machine requires at least one role")
        return self


class FailoverDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str
    active_machine_id: str
    candidate_machine_id: str
    eligible: bool
    reasons: tuple[str, ...]
    required_fencing_token: int = Field(ge=0)
    witness_required: bool = True
    witness_confirmed: bool = False
    reconcile_before_commit: bool = True
    decided_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("decided_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_decision(self) -> FailoverDecision:
        if not RESILIENCE_ID.fullmatch(self.decision_id) or not self.decision_id.startswith(
            "FAILOVER-"
        ):
            raise ValueError("invalid failover decision id")
        if not self.reasons:
            raise ValueError("failover decision requires reasons")
        if self.eligible and self.witness_required and not self.witness_confirmed:
            raise ValueError("eligible fenced failover requires confirmed witness")
        return self


class OperatingModeDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str
    mode: OperatingMode
    failure_domains: tuple[FailureDomain, ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    blocked_capabilities: tuple[str, ...] = ()
    reasons: tuple[str, ...]
    decided_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("decided_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_decision(self) -> OperatingModeDecision:
        if not RESILIENCE_ID.fullmatch(self.decision_id) or not self.decision_id.startswith(
            "MODE-"
        ):
            raise ValueError("invalid operating mode decision id")
        if not self.reasons:
            raise ValueError("operating mode decision requires reasons")
        return self


class HumanRequiredIncident(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    incident_id: str
    failure_domain: FailureDomain
    summary: str = Field(min_length=3, max_length=1000)
    exact_human_action: str = Field(min_length=3, max_length=2000)
    unaffected_work: tuple[str, ...] = ()
    blocked_work: tuple[str, ...] = ()
    verification_steps: tuple[str, ...]
    stale_assumptions_to_invalidate: tuple[str, ...] = ()
    created_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("created_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_incident(self) -> HumanRequiredIncident:
        if not RESILIENCE_ID.fullmatch(self.incident_id) or not self.incident_id.startswith(
            "INCIDENT-"
        ):
            raise ValueError("invalid incident id")
        if not self.verification_steps:
            raise ValueError("human-required incident requires repair verification steps")
        return self


class LocalRuntimeSpec(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    runtime_id: str
    kind: RuntimeKind
    endpoint: str = Field(min_length=8, max_length=500)
    capabilities: tuple[str, ...]
    qualified: bool = False
    advisory_only: Literal[True] = True
    remote_network_allowed: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_runtime(self) -> LocalRuntimeSpec:
        if not RESILIENCE_ID.fullmatch(self.runtime_id) or not self.runtime_id.startswith(
            "RUNTIME-"
        ):
            raise ValueError("invalid runtime id")
        if not self.capabilities:
            raise ValueError("local runtime requires capabilities")
        return self


class BackupRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    backup_id: str
    domain: str
    tool: BackupTool
    repository: str
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    completed: bool
    created_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("created_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_backup(self) -> BackupRecord:
        if not RESILIENCE_ID.fullmatch(self.backup_id) or not self.backup_id.startswith("BACKUP-"):
            raise ValueError("invalid backup id")
        return self


class RestoreVerification(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    restore_id: str
    backup_id: str
    isolated_environment: str = Field(min_length=2, max_length=200)
    state: RestoreState
    checks: tuple[str, ...]
    observed_rpo_seconds: int | None = Field(default=None, ge=0)
    observed_rto_seconds: int | None = Field(default=None, ge=0)
    verified_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("verified_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_restore(self) -> RestoreVerification:
        if not RESILIENCE_ID.fullmatch(self.restore_id) or not self.restore_id.startswith(
            "RESTORE-"
        ):
            raise ValueError("invalid restore id")
        if not self.checks:
            raise ValueError("restore verification requires checks")
        return self
