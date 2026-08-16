from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.contracts.envelopes import ContractModel, EventEnvelope
from project_pipeline.domain.resilience import HumanRequiredIncident


def utc_now() -> datetime:
    return datetime.now(UTC)


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class CommandCenterScope(StrEnum):
    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    INCIDENT = "INCIDENT"


class NotificationLevel(IntEnum):
    INFORMATIONAL = 0
    NOTICE = 1
    ATTENTION = 2
    URGENT = 3
    CRITICAL = 4


class InboxState(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class HealthDimension(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    state: HealthState = HealthState.UNKNOWN
    reason: str = Field(min_length=1, max_length=1000)
    observed_at_utc: datetime = Field(default_factory=utc_now)
    stale: bool = False
    evidence_ids: tuple[str, ...] = ()

    @field_validator("observed_at_utc")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at_utc must be timezone-aware")
        return value.astimezone(UTC)


class ReadinessMetric(ContractModel):
    metric_id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    value: float = Field(ge=0, le=1)
    basis: str = Field(min_length=1, max_length=500)


class LiveWorkItem(ContractModel):
    work_id: str = Field(min_length=1, max_length=191)
    title: str = Field(min_length=1, max_length=300)
    state: str = Field(min_length=1, max_length=100)
    owner: str | None = Field(default=None, max_length=191)
    workspace: str | None = Field(default=None, max_length=512)
    current_stage: str | None = Field(default=None, max_length=191)
    resource_lease_id: str | None = Field(default=None, max_length=191)
    last_progress_at_utc: datetime | None = None
    next_expected_transition: str | None = Field(default=None, max_length=500)
    critical_path: bool = False
    blocked_by: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class CommandCenterSnapshot(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: str = Field(min_length=3, max_length=191)
    project_id: str = Field(min_length=3, max_length=191)
    operating_mode: str = Field(min_length=1, max_length=100)
    overall_health: HealthState
    health: tuple[HealthDimension, ...]
    completion_gate_state: Literal["COMPLETE", "NOT_COMPLETE", "UNKNOWN"] = "UNKNOWN"
    completion_percent: float | None = Field(default=None, ge=0, le=100)
    readiness: tuple[ReadinessMetric, ...] = ()
    live_work: tuple[LiveWorkItem, ...] = ()
    active_incident_ids: tuple[str, ...] = ()
    approval_count: int = Field(default=0, ge=0)
    decision_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    budget_summary: dict[str, Any] = Field(default_factory=dict)
    provider_summary: dict[str, Any] = Field(default_factory=dict)
    context_summary: dict[str, Any] = Field(default_factory=dict)
    canonical_authority: Literal["PROJECT_PIPELINE"] = "PROJECT_PIPELINE"
    ui_state_authoritative: Literal[False] = False
    generated_at_utc: datetime = Field(default_factory=utc_now)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def fingerprint_for(cls, document: dict[str, Any]) -> str:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(payload).hexdigest()


class InboxItem(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    inbox_id: str = Field(min_length=3, max_length=191)
    project_id: str = Field(min_length=3, max_length=191)
    dedupe_key: str = Field(min_length=3, max_length=256)
    kind: str = Field(min_length=1, max_length=100)
    level: NotificationLevel
    title: str = Field(min_length=1, max_length=300)
    impact: str = Field(min_length=1, max_length=1000)
    exact_action: str = Field(min_length=1, max_length=1500)
    post_action_verification: str = Field(min_length=1, max_length=1500)
    deadline_at_utc: datetime | None = None
    critical_path: bool = False
    blocked_tasks: int = Field(default=0, ge=0)
    duration_minutes: int = Field(default=0, ge=0)
    recoverable_automatically: bool = False
    operator_already_aware: bool = False
    priority_score: int = Field(default=0, ge=0)
    state: InboxState = InboxState.OPEN
    correlation_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    created_at_utc: datetime = Field(default_factory=utc_now)
    acknowledged_at_utc: datetime | None = None
    resolved_at_utc: datetime | None = None


class NotificationPolicy(ContractModel):
    quiet_hours_start: int = Field(default=22, ge=0, le=23)
    quiet_hours_end: int = Field(default=7, ge=0, le=23)
    remote_channels_enabled: bool = False
    windows_notifications_enabled: bool = True
    dedupe_window_seconds: int = Field(default=900, ge=0)


class NotificationDecision(ContractModel):
    notification_id: str = Field(min_length=3, max_length=191)
    inbox_id: str = Field(min_length=3, max_length=191)
    level: NotificationLevel
    channels: tuple[str, ...]
    suppressed: bool = False
    suppression_reason: str | None = None
    escalation_required: bool = False
    decided_at_utc: datetime = Field(default_factory=utc_now)


class DirectorMessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class IncidentState(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RECOVERING = "RECOVERING"
    VERIFIED = "VERIFIED"
    RESOLVED = "RESOLVED"


class NotificationDeliveryState(StrEnum):
    CLIENT_ACTION_REQUIRED = "CLIENT_ACTION_REQUIRED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUPPRESSED = "SUPPRESSED"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"


class DirectorActionProposal(ContractModel):
    proposal_id: str = Field(min_length=3, max_length=191)
    command_type: str = Field(min_length=3, max_length=191)
    target: str = Field(min_length=3, max_length=191)
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=3, max_length=1200)
    requires_confirmation: Literal[True] = True
    executes_automatically: Literal[False] = False


class DirectorChatMessage(ContractModel):
    message_id: str = Field(min_length=3, max_length=191)
    conversation_id: str = Field(min_length=3, max_length=191)
    role: DirectorMessageRole
    content: str = Field(min_length=1, max_length=12000)
    actor_id: str | None = Field(default=None, max_length=191)
    scope: CommandCenterScope
    project_id: str = Field(min_length=3, max_length=191)
    incident_id: str | None = Field(default=None, max_length=191)
    snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_ids: tuple[str, ...] = ()
    created_at_utc: datetime = Field(default_factory=utc_now)


class DirectorChatRequest(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    message: str = Field(min_length=1, max_length=12000)
    scope: CommandCenterScope = CommandCenterScope.PROJECT
    incident_id: str | None = Field(default=None, max_length=191)
    conversation_id: str | None = Field(default=None, max_length=191)

    @model_validator(mode="after")
    def validate_scope(self) -> DirectorChatRequest:
        if self.scope is CommandCenterScope.INCIDENT and not self.incident_id:
            raise ValueError("incident scope requires incident_id")
        if self.scope is not CommandCenterScope.INCIDENT and self.incident_id is not None:
            raise ValueError("incident_id is only valid for incident scope")
        return self


class DirectorChatResponse(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    conversation_id: str
    request_message_id: str
    response_message: DirectorChatMessage
    context: DirectorContext
    proposals: tuple[DirectorActionProposal, ...] = ()
    provider_mode: Literal["DETERMINISTIC_GROUNDED", "MODEL_ADAPTER"] = "DETERMINISTIC_GROUNDED"
    private_reasoning_exposed: Literal[False] = False
    canonical_authority: Literal["PROJECT_PIPELINE"] = "PROJECT_PIPELINE"
    raw_text_may_mutate_state: Literal[False] = False


class IncidentVerificationRequest(ContractModel):
    verification_results: dict[str, bool]
    stale_assumptions_invalidated: bool
    reconciliation_complete: bool


class IncidentCase(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    incident: HumanRequiredIncident
    project_id: str = Field(min_length=3, max_length=191)
    state: IncidentState = IncidentState.OPEN
    severity: NotificationLevel = NotificationLevel.URGENT
    inbox_id: str | None = Field(default=None, max_length=191)
    acknowledged_at_utc: datetime | None = None
    recovery_started_at_utc: datetime | None = None
    verified_at_utc: datetime | None = None
    resolved_at_utc: datetime | None = None
    verification: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()


class NotificationDeliveryAttempt(ContractModel):
    delivery_id: str = Field(min_length=3, max_length=191)
    notification_id: str = Field(min_length=3, max_length=191)
    inbox_id: str = Field(min_length=3, max_length=191)
    channel: str = Field(min_length=1, max_length=120)
    adapter_id: str = Field(min_length=1, max_length=120)
    state: NotificationDeliveryState
    attempt_number: int = Field(default=1, ge=1, le=20)
    remote: bool = False
    action_link: str | None = Field(default=None, max_length=1000)
    error_category: str | None = Field(default=None, max_length=191)
    next_retry_at_utc: datetime | None = None
    delivered_at_utc: datetime | None = None
    created_at_utc: datetime = Field(default_factory=utc_now)


class NotificationDispatchResult(ContractModel):
    decision: NotificationDecision
    deliveries: tuple[NotificationDeliveryAttempt, ...]
    remote_delivery_enabled: bool
    canonical_broker: Literal["PROJECT_PIPELINE"] = "PROJECT_PIPELINE"


class TimelinePage(ContractModel):
    after_sequence: int = Field(ge=0)
    next_sequence: int = Field(ge=0)
    has_more: bool
    events: tuple[EventEnvelope, ...]


class DirectorContext(ContractModel):
    scope: CommandCenterScope
    project_id: str
    incident_id: str | None = None
    snapshot_fingerprint: str
    facts: dict[str, Any]
    source_ids: tuple[str, ...] = ()
    private_reasoning_exposed: Literal[False] = False
    proposed_actions_must_be_typed: Literal[True] = True
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def incident_scope_requires_incident(self) -> DirectorContext:
        if self.scope is CommandCenterScope.INCIDENT and not self.incident_id:
            raise ValueError("incident scope requires incident_id")
        return self
