from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel

_MICROUNITS_PER_USD = 1_000_000
BUDGET_ID = re.compile(
    r"^(LIMIT|QUOTA|ENTRY|LEASE|ADMISSION|FORECAST|HISTORY|SIM|ANOMALY|IMPACT)-[A-F0-9]{20}$"
)


def budget_identifier(
    prefix: Literal[
        "LIMIT",
        "QUOTA",
        "ENTRY",
        "LEASE",
        "ADMISSION",
        "FORECAST",
        "HISTORY",
        "SIM",
        "ANOMALY",
        "IMPACT",
    ],
    *parts: str,
) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("budget identifier parts must be non-empty")
    canonical = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20].upper()}"


def budget_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class BudgetScopeType(StrEnum):
    GLOBAL = "GLOBAL"
    PORTFOLIO = "PORTFOLIO"
    PROJECT = "PROJECT"
    PHASE = "PHASE"
    TASK = "TASK"
    PROVIDER = "PROVIDER"
    RESOURCE = "RESOURCE"


class CostClass(StrEnum):
    PROVIDER = "PROVIDER"
    SUBSCRIPTION = "SUBSCRIPTION"
    LOCAL_COMPUTE = "LOCAL_COMPUTE"
    CLOUD = "CLOUD"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    VERIFICATION = "VERIFICATION"
    CONTEXT = "CONTEXT"
    TOOL = "TOOL"
    OTHER = "OTHER"


class CostEvidenceState(StrEnum):
    OBSERVED = "OBSERVED"
    PROVIDER_REPORTED = "PROVIDER_REPORTED"
    ESTIMATED = "ESTIMATED"
    RECONCILED = "RECONCILED"
    INFRACOST = "INFRACOST"
    UNKNOWN = "UNKNOWN"


class LedgerDirection(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class SpendLeaseState(StrEnum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    OVERSPENT = "OVERSPENT"


class PressureMode(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    HARD_STOP = "HARD_STOP"


class ReserveReason(StrEnum):
    P0_FAILURE_RECOVERY = "P0_FAILURE_RECOVERY"
    CRITICAL_PATH = "CRITICAL_PATH"
    RELEASE_BLOCKER = "RELEASE_BLOCKER"
    SECURITY = "SECURITY"
    PRODUCTION_RECOVERY = "PRODUCTION_RECOVERY"
    CRITICAL_ARCHITECTURE = "CRITICAL_ARCHITECTURE"
    DEADLINE_PROTECTION = "DEADLINE_PROTECTION"
    REQUIRED_VERIFICATION = "REQUIRED_VERIFICATION"


class ForecastConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BudgetLimit(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    limit_id: str
    scope_type: BudgetScopeType
    scope_id: str = Field(min_length=1, max_length=191)
    cycle_id: str = Field(min_length=1, max_length=100)
    currency: Literal["USD"] = "USD"
    hard_cap_microunits: int = Field(ge=0)
    soft_cap_microunits: int | None = Field(default=None, ge=0)
    protected_reserve_microunits: int = Field(default=0, ge=0)
    parent_scope_key: str | None = None
    enabled: bool = True

    @property
    def scope_key(self) -> str:
        return f"{self.scope_type.value}:{self.scope_id}"

    @property
    def normal_cap_microunits(self) -> int:
        return self.hard_cap_microunits - self.protected_reserve_microunits

    @model_validator(mode="after")
    def validate_limit(self) -> BudgetLimit:
        if not BUDGET_ID.fullmatch(self.limit_id):
            raise ValueError("invalid budget limit id")
        expected = budget_identifier("LIMIT", self.scope_key, self.cycle_id)
        if self.limit_id != expected:
            raise ValueError("limit_id does not match scope/cycle")
        if (
            self.soft_cap_microunits is not None
            and self.soft_cap_microunits > self.hard_cap_microunits
        ):
            raise ValueError("soft cap cannot exceed hard cap")
        if self.protected_reserve_microunits > self.hard_cap_microunits:
            raise ValueError("protected reserve cannot exceed hard cap")
        return self


class QuotaLimit(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    quota_id: str
    scope_key: str = Field(min_length=3, max_length=250)
    provider_id: str = Field(min_length=1, max_length=191)
    quota_name: str = Field(min_length=1, max_length=100)
    capacity_units: int = Field(gt=0)
    protected_units: int = Field(default=0, ge=0)
    max_shadow_cost_microunits: int = Field(default=0, ge=0)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_quota(self) -> QuotaLimit:
        if self.protected_units > self.capacity_units:
            raise ValueError("protected quota cannot exceed capacity")
        expected = budget_identifier("QUOTA", self.scope_key, self.provider_id, self.quota_name)
        if self.quota_id != expected:
            raise ValueError("quota_id does not match quota semantics")
        return self


class BudgetLedgerEntry(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    entry_id: str
    idempotency_key: str = Field(min_length=1, max_length=300)
    project_id: str = Field(min_length=1, max_length=191)
    task_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    resource_id: str | None = None
    tool_id: str | None = None
    outcome_id: str | None = None
    cost_class: CostClass
    direction: LedgerDirection = LedgerDirection.DEBIT
    cash_microunits: int = Field(default=0, ge=0)
    shadow_cost_microunits: int = Field(default=0, ge=0)
    quota_units: dict[str, int] = Field(default_factory=dict)
    usage_dimensions: dict[str, int] = Field(default_factory=dict)
    scope_keys: tuple[str, ...]
    evidence_state: CostEvidenceState
    verified_outcome: bool = False
    merged_outcome: bool = False
    retry_waste: bool = False
    evidence_references: tuple[str, ...] = ()
    observed_at_utc: datetime
    recorded_at_utc: datetime

    @field_validator("observed_at_utc", "recorded_at_utc")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _aware(value)

    @field_validator("scope_keys")
    @classmethod
    def validate_scope_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(sorted(dict.fromkeys(item.strip() for item in value if item.strip())))
        if not result:
            raise ValueError("ledger entry requires at least one scope key")
        return result

    @field_validator("quota_units", "usage_dimensions")
    @classmethod
    def validate_dimensions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not key.strip() or amount < 0 for key, amount in value.items()):
            raise ValueError(
                "usage/quota dimensions require non-empty keys and non-negative integers"
            )
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def validate_entry(self) -> BudgetLedgerEntry:
        expected = budget_identifier("ENTRY", self.idempotency_key)
        if self.entry_id != expected:
            raise ValueError("entry_id does not match idempotency key")
        if self.cash_microunits == 0 and not self.quota_units and not self.usage_dimensions:
            raise ValueError("ledger entry must record cash, quota, or usage")
        return self

    @property
    def signed_cash_microunits(self) -> int:
        return (
            self.cash_microunits
            if self.direction is LedgerDirection.DEBIT
            else -self.cash_microunits
        )


class SpendLease(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    lease_id: str
    idempotency_key: str = Field(min_length=1, max_length=300)
    project_id: str = Field(min_length=1, max_length=191)
    task_id: str = Field(min_length=1, max_length=191)
    provider_id: str | None = None
    scope_keys: tuple[str, ...]
    maximum_microunits: int = Field(ge=0)
    reserved_microunits: int = Field(ge=0)
    consumed_microunits: int = Field(default=0, ge=0)
    quota_reservations: dict[str, int] = Field(default_factory=dict)
    state: SpendLeaseState = SpendLeaseState.RESERVED
    reserve_reason: ReserveReason | None = None
    reservation_evidence: tuple[str, ...] = ()
    created_at_utc: datetime
    expires_at_utc: datetime
    updated_at_utc: datetime
    reconciliation_required: bool = False

    @field_validator("created_at_utc", "expires_at_utc", "updated_at_utc")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _aware(value)

    @field_validator("scope_keys")
    @classmethod
    def validate_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(sorted(dict.fromkeys(item.strip() for item in value if item.strip())))
        if not result:
            raise ValueError("spend lease requires at least one scope key")
        return result

    @field_validator("quota_reservations")
    @classmethod
    def validate_quota_reservations(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not key.strip() or amount < 0 for key, amount in value.items()):
            raise ValueError("quota reservations require non-negative units")
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def validate_lease(self) -> SpendLease:
        expected = budget_identifier("LEASE", self.idempotency_key)
        if self.lease_id != expected:
            raise ValueError("lease_id does not match idempotency key")
        if self.reserved_microunits > self.maximum_microunits:
            raise ValueError("reserved amount cannot exceed lease maximum")
        if self.expires_at_utc <= self.created_at_utc:
            raise ValueError("lease expiry must follow creation")
        if self.state is SpendLeaseState.UNKNOWN_OUTCOME and not self.reconciliation_required:
            raise ValueError("unknown-outcome leases must require reconciliation")
        return self

    @property
    def reservation_held(self) -> bool:
        return self.state in {SpendLeaseState.RESERVED, SpendLeaseState.UNKNOWN_OUTCOME}


class BudgetPolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    currency: Literal["USD"] = "USD"
    yellow_projected_ratio_milli: int = Field(default=800, ge=1, le=999)
    orange_projected_ratio_milli: int = Field(default=900, ge=1, le=999)
    red_projected_ratio_milli: int = Field(default=975, ge=1, le=999)
    yellow_pace_ratio_milli: int = Field(default=1100, ge=1000)
    orange_pace_ratio_milli: int = Field(default=1250, ge=1000)
    red_pace_ratio_milli: int = Field(default=1500, ge=1000)
    lease_ttl_seconds: int = Field(default=3600, ge=30, le=604800)
    reevaluate_at_consumed_milli: int = Field(default=800, ge=1, le=999)
    default_p90_multiplier_milli: int = Field(default=1500, ge=1000, le=5000)
    minimum_history_samples_medium: int = Field(default=4, ge=1)
    minimum_history_samples_high: int = Field(default=12, ge=2)
    anomaly_warn_ratio_milli: int = Field(default=1500, ge=1000)
    anomaly_block_ratio_milli: int = Field(default=2500, ge=1001)
    reserve_reasons: tuple[ReserveReason, ...] = tuple(ReserveReason)

    @model_validator(mode="after")
    def validate_pressure_order(self) -> BudgetPolicy:
        if (
            not self.yellow_projected_ratio_milli
            < self.orange_projected_ratio_milli
            < self.red_projected_ratio_milli
            < 1000
        ):
            raise ValueError("projected pressure thresholds must increase below 1000")
        if (
            not self.yellow_pace_ratio_milli
            < self.orange_pace_ratio_milli
            < self.red_pace_ratio_milli
        ):
            raise ValueError("pace thresholds must increase")
        if self.anomaly_warn_ratio_milli >= self.anomaly_block_ratio_milli:
            raise ValueError("anomaly warning threshold must be below block threshold")
        return self


class BudgetForecast(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    forecast_id: str
    project_id: str
    task_class: str | None = None
    provider_id: str | None = None
    p50_microunits: int = Field(ge=0)
    p90_microunits: int = Field(ge=0)
    queued_p50_microunits: int = Field(default=0, ge=0)
    queued_p90_microunits: int = Field(default=0, ge=0)
    burn_rate_microunits_per_day: int = Field(default=0, ge=0)
    pace_ratio_milli: int = Field(default=1000, ge=0)
    runway_days_milli: int | None = Field(default=None, ge=0)
    sample_count: int = Field(default=0, ge=0)
    confidence: ForecastConfidence = ForecastConfidence.LOW
    source: str = Field(min_length=1, max_length=100)
    generated_at_utc: datetime

    @field_validator("generated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_forecast(self) -> BudgetForecast:
        if (
            self.p90_microunits < self.p50_microunits
            or self.queued_p90_microunits < self.queued_p50_microunits
        ):
            raise ValueError("P90 forecast cannot be below P50")
        expected = budget_identifier(
            "FORECAST",
            self.project_id,
            self.task_class or "*",
            self.provider_id or "*",
            self.generated_at_utc.isoformat(),
        )
        if self.forecast_id != expected:
            raise ValueError("forecast_id does not match forecast semantics")
        return self


class BudgetSnapshot(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    scope_key: str
    hard_cap_microunits: int = Field(ge=0)
    soft_cap_microunits: int = Field(ge=0)
    protected_reserve_microunits: int = Field(ge=0)
    spent_microunits: int = Field(ge=0)
    credited_microunits: int = Field(ge=0)
    committed_microunits: int = Field(ge=0)
    remaining_normal_microunits: int = Field(ge=0)
    remaining_total_microunits: int = Field(ge=0)
    forecast_p90_microunits: int = Field(default=0, ge=0)
    pace_ratio_milli: int = Field(default=1000, ge=0)
    pressure_mode: PressureMode
    observed_at_utc: datetime

    @field_validator("observed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)


class BudgetAdmissionRequest(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str = Field(min_length=1, max_length=191)
    task_id: str = Field(min_length=1, max_length=191)
    task_class: str = Field(min_length=1, max_length=100)
    provider_id: str | None = None
    scope_keys: tuple[str, ...]
    estimated_p50_microunits: int = Field(ge=0)
    estimated_p90_microunits: int = Field(ge=0)
    quota_requirements: dict[str, int] = Field(default_factory=dict)
    priority: str = "P2"
    risk: str = "MEDIUM"
    critical_path: bool = False
    required_verification: bool = False
    paid_incremental: bool = True
    local_or_subscription_alternative: bool = False
    reserve_reason: ReserveReason | None = None
    deadline_at_utc: datetime | None = None

    @field_validator("scope_keys")
    @classmethod
    def validate_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(sorted(dict.fromkeys(item.strip() for item in value if item.strip())))
        if not result:
            raise ValueError("admission request requires scope keys")
        return result

    @field_validator("deadline_at_utc")
    @classmethod
    def validate_deadline(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)

    @field_validator("quota_requirements")
    @classmethod
    def validate_quota_requirements(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not key.strip() or units < 0 for key, units in value.items()):
            raise ValueError("quota requirements require non-negative units")
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def validate_estimate(self) -> BudgetAdmissionRequest:
        if self.estimated_p90_microunits < self.estimated_p50_microunits:
            raise ValueError("estimated P90 cannot be below P50")
        return self


class BudgetAdmissionDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str
    task_id: str
    admitted: bool
    pressure_mode: PressureMode
    authorized_microunits: int = Field(ge=0)
    reserve_authorized: bool = False
    allowed_paid_incremental: bool = True
    quota_shadow_cost_microunits: int = Field(default=0, ge=0)
    reasons: tuple[str, ...] = ()
    preferred_execution_modes: tuple[str, ...] = ()
    generated_at_utc: datetime

    @field_validator("generated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)


class CostHistoryObservation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    observation_id: str
    project_id: str
    task_id: str
    task_class: str
    provider_id: str | None = None
    cash_microunits: int = Field(ge=0)
    shadow_cost_microunits: int = Field(default=0, ge=0)
    succeeded: bool
    verified: bool
    merged: bool = False
    retry_count: int = Field(default=0, ge=0)
    rework_count: int = Field(default=0, ge=0)
    observed_at_utc: datetime

    @field_validator("observed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_observation(self) -> CostHistoryObservation:
        expected = budget_identifier(
            "HISTORY",
            self.project_id,
            self.task_id,
            self.provider_id or "*",
            self.observed_at_utc.isoformat(),
        )
        if self.observation_id != expected:
            raise ValueError("observation_id does not match history semantics")
        return self


class CostOutcomeMetrics(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    total_cost_microunits: int = Field(ge=0)
    verified_outcome_count: int = Field(ge=0)
    merged_outcome_count: int = Field(ge=0)
    wasted_cost_microunits: int = Field(ge=0)
    cost_per_verified_outcome_microunits: int | None = Field(default=None, ge=0)
    cost_per_merged_outcome_microunits: int | None = Field(default=None, ge=0)


class BudgetAnomaly(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    anomaly_id: str
    project_id: str
    task_id: str | None = None
    provider_id: str | None = None
    expected_p90_microunits: int = Field(ge=0)
    observed_microunits: int = Field(ge=0)
    observed_to_expected_milli: int = Field(ge=0)
    severity: Literal["NORMAL", "WARN", "BLOCK"]
    block_new_paid_work: bool = False
    reasons: tuple[str, ...] = ()
    detected_at_utc: datetime

    @field_validator("detected_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)


class BudgetChangeImpact(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    impact_id: str
    scope_key: str
    old_hard_cap_microunits: int = Field(ge=0)
    new_hard_cap_microunits: int = Field(ge=0)
    active_commitment_microunits: int = Field(ge=0)
    committed_over_new_cap_microunits: int = Field(ge=0)
    active_lease_count: int = Field(ge=0)
    requires_operator_attention: bool
    generated_at_utc: datetime

    @field_validator("generated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)


class InfracostEstimate(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    available: bool
    complete: bool
    currency: str | None = None
    total_hourly_microunits: int | None = Field(default=None, ge=0)
    total_monthly_microunits: int | None = Field(default=None, ge=0)
    total_monthly_usage_microunits: int | None = Field(default=None, ge=0)
    unknown_price_components: int = Field(default=0, ge=0)
    project_count: int = Field(default=0, ge=0)
    source_revision: str | None = None
    reasons: tuple[str, ...] = ()


class BudgetSimulationResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    simulation_id: str
    scenario: str
    pressure_mode: PressureMode
    admitted_tasks: tuple[str, ...]
    denied_tasks: tuple[str, ...]
    spent_microunits: int = Field(ge=0)
    committed_microunits: int = Field(ge=0)
    remaining_microunits: int = Field(ge=0)
    notes: tuple[str, ...] = ()
    generated_at_utc: datetime

    @field_validator("generated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)


__all__ = [
    "_MICROUNITS_PER_USD",
    "BudgetAdmissionDecision",
    "BudgetAdmissionRequest",
    "BudgetAnomaly",
    "BudgetChangeImpact",
    "BudgetForecast",
    "BudgetLedgerEntry",
    "BudgetLimit",
    "BudgetPolicy",
    "BudgetScopeType",
    "BudgetSimulationResult",
    "BudgetSnapshot",
    "CostClass",
    "CostEvidenceState",
    "CostHistoryObservation",
    "CostOutcomeMetrics",
    "ForecastConfidence",
    "InfracostEstimate",
    "LedgerDirection",
    "PressureMode",
    "QuotaLimit",
    "ReserveReason",
    "SpendLease",
    "SpendLeaseState",
    "budget_fingerprint",
    "budget_identifier",
]
