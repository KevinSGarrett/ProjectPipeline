from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel
from project_pipeline.domain.scheduler import ResourceClaim

ROUTER_ID = re.compile(r"^(ROUTE|ATTEMPT|PERF|QUAL|REG)-[A-F0-9]{20}$")
CAPABILITY = re.compile(r"^[a-z][a-z0-9_]{2,80}$")
ENTITY_ID = re.compile(r"^(provider|model|agent|tool|adapter):[a-z0-9][a-z0-9._:-]{1,126}$")


def router_identifier(
    prefix: Literal["ROUTE", "ATTEMPT", "PERF", "QUAL", "REG"], *parts: str
) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("router identifier parts must be non-empty")
    canonical = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20].upper()}"


def agent_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProviderRuntimeState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_LOW = "QUOTA_LOW"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    AUTH_FAILED = "AUTH_FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"
    MAINTENANCE = "MAINTENANCE"
    RECOVERING = "RECOVERING"


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class QualificationState(StrEnum):
    QUARANTINED = "QUARANTINED"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExecutionMode(StrEnum):
    LOCAL_PROCESS = "LOCAL_PROCESS"
    HOSTED_API = "HOSTED_API"
    SUBSCRIPTION_TOOL = "SUBSCRIPTION_TOOL"
    BROWSER = "BROWSER"
    MOCK = "MOCK"


class AuthorityClass(StrEnum):
    ADVISORY = "ADVISORY"
    IMPLEMENTATION = "IMPLEMENTATION"
    REVIEW = "REVIEW"
    VERIFICATION = "VERIFICATION"
    RECOVERY = "RECOVERY"
    STEWARDSHIP = "STEWARDSHIP"


class CapabilitySpec(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    capability_id: str
    description: str = Field(min_length=1, max_length=1000)
    task_classes: tuple[str, ...] = ()
    quality_tiers: tuple[str, ...] = ("standard",)
    requires_tools: tuple[str, ...] = ()
    risk_ceiling: str = "HIGH"

    @field_validator("capability_id")
    @classmethod
    def valid_capability(cls, value: str) -> str:
        value = value.strip().lower()
        if not CAPABILITY.fullmatch(value):
            raise ValueError("capability_id must be lower snake case")
        return value


class ProviderSpec(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    provider_id: str
    display_name: str = Field(min_length=1, max_length=191)
    adapter_id: str
    execution_mode: ExecutionMode
    capabilities: tuple[str, ...]
    enabled: bool = True
    local: bool = False
    subscription_backed: bool = False
    data_egress: bool = True
    cost_behavior: str = "unknown"
    constraints: tuple[str, ...] = ()
    resource_claims: tuple[ResourceClaim, ...] = ()

    @field_validator("provider_id", "adapter_id")
    @classmethod
    def valid_entity(cls, value: str) -> str:
        value = value.strip().lower()
        if not ENTITY_ID.fullmatch(value):
            raise ValueError("provider and adapter identifiers must be stable namespaced IDs")
        return value

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(dict.fromkeys(item.strip().lower() for item in value))
        if not result or any(not CAPABILITY.fullmatch(item) for item in result):
            raise ValueError("provider capabilities must be non-empty lower snake case identifiers")
        return result


class ModelSpec(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    model_id: str
    provider_id: str
    provider_model_name: str = Field(min_length=1, max_length=191)
    version: str = Field(min_length=1, max_length=191)
    capabilities: tuple[str, ...]
    quality_tier: str = "standard"
    qualification: QualificationState = QualificationState.QUARANTINED
    context_limit: int | None = Field(default=None, ge=1)
    output_limit: int | None = Field(default=None, ge=1)
    local: bool = False
    resource_claims: tuple[ResourceClaim, ...] = ()

    @field_validator("model_id", "provider_id")
    @classmethod
    def valid_entity(cls, value: str) -> str:
        value = value.strip().lower()
        if not ENTITY_ID.fullmatch(value):
            raise ValueError("model/provider identifiers must be stable namespaced IDs")
        return value

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(dict.fromkeys(item.strip().lower() for item in value))
        if not result or any(not CAPABILITY.fullmatch(item) for item in result):
            raise ValueError("model capabilities must be non-empty lower snake case identifiers")
        return result


class ToolSpec(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    tool_id: str
    adapter_id: str
    version: str
    capabilities: tuple[str, ...]
    qualification: QualificationState = QualificationState.QUARANTINED
    mutating: bool = False
    required_authority_scope: tuple[str, ...] = ()

    @field_validator("tool_id", "adapter_id")
    @classmethod
    def valid_entity(cls, value: str) -> str:
        value = value.strip().lower()
        if not ENTITY_ID.fullmatch(value):
            raise ValueError("tool/adapter identifiers must be stable namespaced IDs")
        return value


class AgentSpec(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    agent_id: str
    model_id: str
    capabilities: tuple[str, ...]
    authority_classes: tuple[AuthorityClass, ...] = (AuthorityClass.ADVISORY,)
    qualification: QualificationState = QualificationState.QUARANTINED
    tool_ids: tuple[str, ...] = ()

    @field_validator("agent_id", "model_id")
    @classmethod
    def valid_entity(cls, value: str) -> str:
        value = value.strip().lower()
        if not ENTITY_ID.fullmatch(value):
            raise ValueError("agent/model identifiers must be stable namespaced IDs")
        return value


class CapabilityRoutePolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    capability_id: str
    preferred_provider_ids: tuple[str, ...] = ()
    fallback_provider_ids: tuple[str, ...] = ()
    prefer_local_under_pressure: bool = True

    @field_validator("capability_id")
    @classmethod
    def valid_capability(cls, value: str) -> str:
        value = value.strip().lower()
        if not CAPABILITY.fullmatch(value):
            raise ValueError("invalid capability_id")
        return value


class AgentRegistrySnapshot(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    registry_id: str
    capabilities: tuple[CapabilitySpec, ...]
    providers: tuple[ProviderSpec, ...]
    models: tuple[ModelSpec, ...]
    agents: tuple[AgentSpec, ...]
    tools: tuple[ToolSpec, ...] = ()
    routing_policies: tuple[CapabilityRoutePolicy, ...] = ()
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_links(self) -> AgentRegistrySnapshot:
        providers = {item.provider_id for item in self.providers}
        models = {item.model_id: item for item in self.models}
        tools = {item.tool_id for item in self.tools}
        capabilities = {item.capability_id for item in self.capabilities}
        for model in self.models:
            if model.provider_id not in providers:
                raise ValueError(f"model references unknown provider: {model.provider_id}")
            if not set(model.capabilities) <= capabilities:
                raise ValueError(f"model references unknown capabilities: {model.model_id}")
        for agent in self.agents:
            if agent.model_id not in models:
                raise ValueError(f"agent references unknown model: {agent.model_id}")
            if not set(agent.capabilities) <= capabilities:
                raise ValueError(f"agent references unknown capabilities: {agent.agent_id}")
            if not set(agent.tool_ids) <= tools:
                raise ValueError(f"agent references unknown tools: {agent.agent_id}")
        for provider in self.providers:
            if not set(provider.capabilities) <= capabilities:
                raise ValueError(
                    f"provider references unknown capabilities: {provider.provider_id}"
                )
        return self


class ProviderStateObservation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    provider_id: str
    state: ProviderRuntimeState
    reason: str = ""
    observed_at_utc: datetime
    retry_after_utc: datetime | None = None
    quota_remaining_milli: int | None = Field(default=None, ge=0, le=1000)


class CircuitBreakerPolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    failure_threshold: int = Field(default=3, ge=1, le=100)
    recovery_seconds: int = Field(default=120, ge=1, le=86400)
    half_open_probe_limit: int = Field(default=1, ge=1, le=10)


class CircuitBreakerRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    provider_id: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = Field(default=0, ge=0)
    opened_at_utc: datetime | None = None
    half_open_probes: int = Field(default=0, ge=0)
    last_failure: str | None = None
    updated_at_utc: datetime

    def permits(self, when: datetime, policy: CircuitBreakerPolicy) -> bool:
        when = when.astimezone(UTC)
        if self.state is CircuitState.CLOSED:
            return True
        if self.state is CircuitState.HALF_OPEN:
            return self.half_open_probes < policy.half_open_probe_limit
        if self.opened_at_utc is None:
            return False
        return when >= self.opened_at_utc.astimezone(UTC) + timedelta(
            seconds=policy.recovery_seconds
        )


class NormalizedUsage(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    input_units: int = Field(default=0, ge=0)
    output_units: int = Field(default=0, ge=0)
    cached_input_units: int = Field(default=0, ge=0)
    request_count: int = Field(default=1, ge=0)
    cost_microunits: int | None = Field(default=None, ge=0)


class ExecutionTaskContract(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str = Field(min_length=1, max_length=191)
    task_class: str = Field(min_length=1, max_length=100)
    required_capabilities: tuple[str, ...]
    quality_tier: str = "standard"
    risk: str = "MEDIUM"
    instructions: str = Field(min_length=1, max_length=100_000)
    context: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    maximum_cost_microunits: int | None = Field(default=None, ge=0)
    allow_data_egress: bool = True
    allow_degraded: bool = True
    allow_canary: bool = False

    @field_validator("required_capabilities")
    @classmethod
    def valid_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(dict.fromkeys(item.strip().lower() for item in value))
        if not result or any(not CAPABILITY.fullmatch(item) for item in result):
            raise ValueError("required_capabilities must be non-empty lower snake case")
        return result


class ProviderInvocationResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    provider_id: str
    model_id: str | None = None
    agent_id: str | None = None
    output: dict[str, Any]
    usage: NormalizedUsage = Field(default_factory=NormalizedUsage)
    provider_request_id: str | None = None
    finish_reason: str | None = None
    evidence_references: tuple[str, ...] = ()


class PerformanceObservation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    observation_id: str
    target_id: str
    capability_id: str
    task_class: str
    success: bool
    latency_ms: int = Field(ge=0)
    cost_microunits: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    rework_count: int = Field(default=0, ge=0)
    review_findings: int = Field(default=0, ge=0)
    quality_milli: int = Field(default=500, ge=0, le=1000)
    observed_at_utc: datetime


class PerformanceSummary(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    target_id: str
    capability_id: str
    sample_count: int = Field(ge=0)
    success_milli: int = Field(ge=0, le=1000)
    quality_milli: int = Field(ge=0, le=1000)
    mean_latency_ms: int = Field(ge=0)
    mean_cost_microunits: int | None = Field(default=None, ge=0)


class RouteCandidate(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    agent_id: str
    model_id: str
    provider_id: str
    adapter_id: str
    eligible: bool
    reasons: tuple[str, ...] = ()
    fallback_rank: int = Field(default=9999, ge=0)
    score: int = 0
    provider_state: ProviderRuntimeState
    circuit_state: CircuitState
    qualification: QualificationState
    performance: PerformanceSummary | None = None


class RoutingDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str
    request_fingerprint: str
    task_id: str
    required_capabilities: tuple[str, ...]
    candidates: tuple[RouteCandidate, ...]
    selected_agent_id: str | None = None
    selected_model_id: str | None = None
    selected_provider_id: str | None = None
    generated_at_utc: datetime
    no_route_reasons: tuple[str, ...] = ()


class QualificationCheckResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    check_name: str
    passed: bool
    detail: str = ""


class AdapterQualificationReport(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    report_id: str
    subject_id: str
    subject_version: str
    checks: tuple[QualificationCheckResult, ...]
    state: QualificationState
    evaluated_at_utc: datetime
    rollback_ready: bool = False


class ExecutionAttempt(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    attempt_id: str
    provider_id: str
    model_id: str
    agent_id: str
    succeeded: bool
    retryable: bool = False
    error_kind: str | None = None
    error_message: str | None = None
    result: ProviderInvocationResult | None = None
    started_at_utc: datetime
    finished_at_utc: datetime


class ExecutionReceipt(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: str
    task_id: str
    routing_decision_id: str
    attempts: tuple[ExecutionAttempt, ...]
    succeeded: bool
    result: ProviderInvocationResult | None = None
    generated_at_utc: datetime
