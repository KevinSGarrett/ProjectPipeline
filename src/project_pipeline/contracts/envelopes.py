from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[
    str,
    Field(min_length=3, max_length=191, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class CommandStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalState(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


def utc_now() -> datetime:
    return datetime.now(UTC)


def generated_id(prefix: str) -> str:
    return f"{prefix}:{uuid4()}"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ActionIntent(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    action_id: Identifier = Field(default_factory=lambda: generated_id("action"))
    actor_id: Identifier
    authority: Identifier
    target: str = Field(min_length=1, max_length=512)
    operation: Identifier
    scope: tuple[str, ...] = ()
    risk: RiskLevel = RiskLevel.MEDIUM
    idempotency_key: str = Field(min_length=8, max_length=256)
    approval_state: ApprovalState = ApprovalState.REQUIRED
    correlation_id: Identifier


class CommandEnvelope(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    command_id: Identifier = Field(default_factory=lambda: generated_id("command"))
    command_type: Identifier
    project_id: Identifier
    actor_id: Identifier
    correlation_id: Identifier
    idempotency_key: str = Field(min_length=8, max_length=256)
    issued_at_utc: datetime = Field(default_factory=utc_now)
    authority_scope: tuple[str, ...] = ()
    dry_run: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    action_intent: ActionIntent | None = None

    @field_validator("issued_at_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("issued_at_utc must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def align_action_intent(self) -> CommandEnvelope:
        if self.action_intent is None:
            return self
        if self.action_intent.actor_id != self.actor_id:
            raise ValueError("action intent actor must match command actor")
        if self.action_intent.correlation_id != self.correlation_id:
            raise ValueError("action intent correlation ID must match command correlation ID")
        if self.action_intent.idempotency_key != self.idempotency_key:
            raise ValueError("action intent idempotency key must match command idempotency key")
        return self

    def semantic_fingerprint(self) -> str:
        document = self.model_dump(mode="json", exclude={"command_id", "issued_at_utc"})
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class StateTransition(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    transition_id: Identifier = Field(default_factory=lambda: generated_id("transition"))
    entity_type: Identifier
    entity_id: Identifier
    previous_state: str | None = None
    next_state: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    command_id: Identifier
    correlation_id: Identifier
    occurred_at_utc: datetime = Field(default_factory=utc_now)
    evidence_ids: tuple[str, ...] = ()

    @field_validator("occurred_at_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at_utc must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def reject_noop(self) -> StateTransition:
        if self.previous_state is not None and self.previous_state == self.next_state:
            raise ValueError("state transition must change state")
        return self


class EventEnvelope(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: Identifier = Field(default_factory=lambda: generated_id("event"))
    event_type: Identifier
    project_id: Identifier
    producer: Identifier
    correlation_id: Identifier
    aggregate_type: Identifier
    aggregate_id: Identifier
    occurred_at_utc: datetime = Field(default_factory=utc_now)
    causation_id: Identifier | None = None
    actor_id: Identifier | None = None
    workflow_id: Identifier | None = None
    task_id: Identifier | None = None
    run_id: Identifier | None = None
    sequence: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()

    @field_validator("occurred_at_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at_utc must be timezone-aware")
        return value.astimezone(UTC)


class CommandResult(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    command_id: Identifier
    command_type: Identifier
    project_id: Identifier
    correlation_id: Identifier
    idempotency_key: str = Field(min_length=8, max_length=256)
    status: CommandStatus
    replayed: bool = False
    completed_at_utc: datetime = Field(default_factory=utc_now)
    output: dict[str, Any] = Field(default_factory=dict)
    transitions: tuple[StateTransition, ...] = ()
    events: tuple[EventEnvelope, ...] = ()
    error: dict[str, Any] | None = None

    @field_validator("completed_at_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at_utc must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_error_state(self) -> CommandResult:
        if self.status is CommandStatus.SUCCEEDED and self.error is not None:
            raise ValueError("successful command result cannot contain an error")
        if self.status in {CommandStatus.FAILED, CommandStatus.UNKNOWN} and self.error is None:
            raise ValueError("failed or unknown command result must contain an error")
        return self
