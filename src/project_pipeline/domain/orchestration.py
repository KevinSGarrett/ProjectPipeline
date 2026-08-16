from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel

_ID_PREFIXES = {
    "workflow_definition": "WFDEF",
    "workflow": "WFRUN",
    "event": "WFEVT",
    "wait": "WFWAIT",
    "checkpoint": "WFCHK",
    "operation": "WFOP",
    "recovery": "WFREC",
    "signal": "WFSIG",
}


def orchestration_identifier(kind: str, *parts: str) -> str:
    prefix = _ID_PREFIXES.get(kind)
    if prefix is None:
        raise ValueError(f"unsupported orchestration identifier kind: {kind}")
    if not parts or not any(str(part).strip() for part in parts):
        raise ValueError("orchestration identifier requires at least one non-empty part")
    canonical = "\x1f".join(str(part).strip() for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24].upper()
    return f"{prefix}-{digest}"


def canonical_payload_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


class DurableBackendKind(StrEnum):
    LOCAL_REFERENCE = "LOCAL_REFERENCE"
    HATCHET = "HATCHET"
    DBOS = "DBOS"
    TEMPORAL = "TEMPORAL"
    MOCK = "MOCK"


class WorkflowState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUSPENDED = "SUSPENDED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class StepState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WaitKind(StrEnum):
    SIGNAL = "SIGNAL"
    UNTIL = "UNTIL"


class DurableOperationState(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    RECONCILED = "RECONCILED"
    FAILED = "FAILED"


class RecoveryAction(StrEnum):
    NO_ACTION = "NO_ACTION"
    RETRY_STEP = "RETRY_STEP"
    RESUME_WAIT = "RESUME_WAIT"
    MARK_RECOVERY_REQUIRED = "MARK_RECOVERY_REQUIRED"
    RECONCILE_OPERATION = "RECONCILE_OPERATION"
    RELEASE_STALE_RESOURCES = "RELEASE_STALE_RESOURCES"
    CANCEL = "CANCEL"


class BackendQualificationState(StrEnum):
    LOCAL_VERIFIED = "LOCAL_VERIFIED"
    ADAPTER_IMPLEMENTED = "ADAPTER_IMPLEMENTED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
    LIVE_VERIFIED = "LIVE_VERIFIED"


class RetryPolicy(DomainModel):
    max_attempts: int = Field(default=3, ge=1, le=100)
    initial_backoff_seconds: float = Field(default=1.0, ge=0.0, le=86400.0)
    multiplier: float = Field(default=2.0, ge=1.0, le=100.0)
    max_backoff_seconds: float = Field(default=60.0, ge=0.0, le=604800.0)

    @model_validator(mode="after")
    def validate_backoff(self) -> RetryPolicy:
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds cannot be less than initial_backoff_seconds")
        return self

    def backoff_seconds(self, failed_attempt: int) -> float:
        if failed_attempt < 1:
            raise ValueError("failed_attempt must be at least 1")
        return min(
            self.max_backoff_seconds,
            self.initial_backoff_seconds * (self.multiplier ** (failed_attempt - 1)),
        )


class WorkflowStepDefinition(DomainModel):
    step_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    name: str = Field(min_length=1, max_length=240)
    retry_policy: RetryPolicy = RetryPolicy()
    execution_timeout_seconds: int = Field(default=900, ge=1, le=604800)
    schedule_timeout_seconds: int = Field(default=3600, ge=1, le=2592000)
    recoverable: bool = True
    requires_checkpoint: bool = False


class WorkflowDefinition(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    definition_id: str
    workflow_name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    steps: tuple[WorkflowStepDefinition, ...]

    @model_validator(mode="after")
    def validate_definition(self) -> WorkflowDefinition:
        expected = orchestration_identifier("workflow_definition", self.workflow_name, self.version)
        if self.definition_id != expected:
            raise ValueError("definition_id does not match workflow name/version")
        ids = [item.step_id for item in self.steps]
        if not ids:
            raise ValueError("workflow definition requires at least one step")
        if len(ids) != len(set(ids)):
            raise ValueError("workflow step identifiers must be unique")
        return self


class WorkflowStartRequest(DomainModel):
    definition_id: str
    idempotency_key: str = Field(min_length=1, max_length=300)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    backend: DurableBackendKind = DurableBackendKind.LOCAL_REFERENCE


class WorkflowInstance(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    workflow_id: str
    definition_id: str
    idempotency_key: str
    state: WorkflowState
    version: int = Field(ge=1)
    backend: DurableBackendKind
    backend_run_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    current_step_index: int = Field(default=0, ge=0)
    current_attempt: int = Field(default=0, ge=0)
    assigned_worker_id: str | None = None
    wait_id: str | None = None
    last_checkpoint_id: str | None = None
    retry_available_at_utc: datetime | None = None
    cancel_requested: bool = False
    recovery_count: int = Field(default=0, ge=0)
    failure_code: str | None = None
    failure_message: str | None = None
    created_at_utc: datetime
    updated_at_utc: datetime

    @field_validator("created_at_utc", "updated_at_utc", "retry_available_at_utc")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_aware(value)

    @model_validator(mode="after")
    def validate_instance(self) -> WorkflowInstance:
        expected = orchestration_identifier("workflow", self.definition_id, self.idempotency_key)
        if self.workflow_id != expected:
            raise ValueError("workflow_id does not match definition/idempotency key")
        if self.updated_at_utc < self.created_at_utc:
            raise ValueError("updated_at_utc cannot precede created_at_utc")
        if self.state == WorkflowState.WAITING and not self.wait_id:
            raise ValueError("WAITING workflows require wait_id")
        if self.state == WorkflowState.RETRY_SCHEDULED and self.retry_available_at_utc is None:
            raise ValueError("RETRY_SCHEDULED workflows require retry_available_at_utc")
        return self


class WorkflowEvent(DomainModel):
    event_id: str
    workflow_id: str
    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")
    occurred_at_utc: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None

    @field_validator("occurred_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_id(self) -> WorkflowEvent:
        expected = orchestration_identifier(
            "event", self.workflow_id, str(self.sequence), self.event_type
        )
        if self.event_id != expected:
            raise ValueError("event_id does not match workflow sequence/type")
        return self


class DurableWait(DomainModel):
    wait_id: str
    workflow_id: str
    kind: WaitKind
    signal_name: str | None = None
    release_at_utc: datetime | None = None
    created_at_utc: datetime
    satisfied_at_utc: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at_utc", "release_at_utc", "satisfied_at_utc")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_aware(value)

    @model_validator(mode="after")
    def validate_wait(self) -> DurableWait:
        if self.kind == WaitKind.SIGNAL and not self.signal_name:
            raise ValueError("SIGNAL waits require signal_name")
        if self.kind == WaitKind.UNTIL and self.release_at_utc is None:
            raise ValueError("UNTIL waits require release_at_utc")
        expected = orchestration_identifier(
            "wait",
            self.workflow_id,
            self.kind.value,
            self.signal_name or "",
            self.release_at_utc.isoformat() if self.release_at_utc else "",
        )
        if self.wait_id != expected:
            raise ValueError("wait_id does not match wait semantics")
        return self


class WorkflowCheckpoint(DomainModel):
    checkpoint_id: str
    workflow_id: str
    step_id: str
    attempt: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at_utc: datetime

    @field_validator("created_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_checkpoint(self) -> WorkflowCheckpoint:
        if self.payload_sha256 != canonical_payload_sha256(self.payload):
            raise ValueError("checkpoint payload hash mismatch")
        expected = orchestration_identifier(
            "checkpoint", self.workflow_id, self.step_id, str(self.attempt), self.payload_sha256
        )
        if self.checkpoint_id != expected:
            raise ValueError("checkpoint_id does not match checkpoint content")
        return self


class WorkerHeartbeat(DomainModel):
    worker_id: str = Field(min_length=1, max_length=200)
    fencing_epoch: int = Field(ge=1)
    observed_at_utc: datetime
    expires_at_utc: datetime
    capabilities: tuple[str, ...] = ()
    active_workflow_ids: tuple[str, ...] = ()

    @field_validator("observed_at_utc", "expires_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> WorkerHeartbeat:
        if self.expires_at_utc <= self.observed_at_utc:
            raise ValueError("worker heartbeat expiry must follow observation")
        return self


class DurableOperation(DomainModel):
    operation_id: str
    workflow_id: str
    operation_type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")
    idempotency_key: str = Field(min_length=1, max_length=300)
    state: DurableOperationState
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    backend: DurableBackendKind
    backend_operation_id: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    created_at_utc: datetime
    updated_at_utc: datetime

    @field_validator("created_at_utc", "updated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_operation(self) -> DurableOperation:
        if self.payload_sha256 != canonical_payload_sha256(self.payload):
            raise ValueError("operation payload hash mismatch")
        expected = orchestration_identifier(
            "operation", self.workflow_id, self.operation_type, self.idempotency_key
        )
        if self.operation_id != expected:
            raise ValueError("operation_id does not match workflow/type/idempotency key")
        if self.updated_at_utc < self.created_at_utc:
            raise ValueError("operation update time cannot precede creation")
        return self


class RecoveryDecision(DomainModel):
    recovery_id: str
    workflow_id: str
    action: RecoveryAction
    reason_codes: tuple[str, ...]
    created_at_utc: datetime
    worker_id: str | None = None
    operation_id: str | None = None
    safe_to_automate: bool = False

    @field_validator("created_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_recovery(self) -> RecoveryDecision:
        if not self.reason_codes:
            raise ValueError("recovery decision requires at least one reason code")
        expected = orchestration_identifier(
            "recovery",
            self.workflow_id,
            self.action.value,
            "|".join(self.reason_codes),
            self.worker_id or "",
            self.operation_id or "",
        )
        if self.recovery_id != expected:
            raise ValueError("recovery_id does not match recovery decision")
        return self


class WorkflowSignal(DomainModel):
    signal_id: str
    workflow_id: str
    signal_name: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    idempotency_key: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    observed_at_utc: datetime

    @field_validator("observed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_signal(self) -> WorkflowSignal:
        expected = orchestration_identifier(
            "signal", self.workflow_id, self.signal_name, self.idempotency_key
        )
        if self.signal_id != expected:
            raise ValueError("signal_id does not match signal identity")
        return self


class BackendCapabilities(DomainModel):
    backend: DurableBackendKind
    supports_signals: bool
    supports_timers: bool
    supports_retries: bool
    supports_cancel: bool
    supports_query: bool
    supports_native_recovery: bool
    qualification: BackendQualificationState
    detail: str = ""


class OrchestrationPolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    initial_backend: DurableBackendKind = DurableBackendKind.HATCHET
    fallback_backends: tuple[DurableBackendKind, ...] = (
        DurableBackendKind.DBOS,
        DurableBackendKind.TEMPORAL,
    )
    allow_active_backend_migration: bool = False
    blind_retry_unknown_outcome: bool = False
    worker_heartbeat_ttl_seconds: int = Field(default=60, ge=5, le=3600)
    recover_stale_workers: bool = True
    max_automated_recovery_count: int = Field(default=5, ge=0, le=100)

    @model_validator(mode="after")
    def validate_policy(self) -> OrchestrationPolicy:
        if self.initial_backend in self.fallback_backends:
            raise ValueError("initial backend cannot also be a fallback backend")
        if len(self.fallback_backends) != len(set(self.fallback_backends)):
            raise ValueError("fallback backend list contains duplicates")
        return self


class OrchestrationSimulationResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    scenario: str = Field(min_length=1, max_length=100)
    passed: bool
    observations: tuple[str, ...]
    final_state: str


class BackendMutationReceipt(DomainModel):
    backend: DurableBackendKind
    accepted: bool
    backend_operation_id: str | None = None
    backend_run_id: str | None = None
    unknown_outcome: bool = False
    detail: str = ""


class BackendRunObservation(DomainModel):
    backend: DurableBackendKind
    backend_run_id: str
    state: str = Field(min_length=1, max_length=100)
    observed_at_utc: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at_utc")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _require_aware(value)


class OrchestrationStatus(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    definitions: int = Field(ge=0)
    workflows: int = Field(ge=0)
    active_workflows: int = Field(ge=0)
    waiting_workflows: int = Field(ge=0)
    recovery_required: int = Field(ge=0)
    unknown_outcomes: int = Field(ge=0)
    stale_workers: int = Field(ge=0)
