from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator

from project_pipeline.domain.base import DomainModel

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
REQUIRED_HEALTH_LAYERS = (
    "component",
    "project",
    "provider",
    "synchronization",
    "budget",
    "evidence",
)
DEFAULT_FRESHNESS_SECONDS = 3600
DEFAULT_RETENTION_DAYS = 30
REDACTED_FIELDS = frozenset(
    {
        "token",
        "secret",
        "password",
        "authorization",
        "api_key",
        "apikey",
        "credential",
        "access_key",
        "private_key",
    }
)


def ops_identifier(*parts: str) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("ops identifier parts must be non-empty")
    payload = "\x1f".join(str(part).strip() for part in parts)
    return f"OPS-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def canonical_payload(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_payload(value).encode("utf-8")).hexdigest()


class LayerState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class WorkerResult(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class FailureClass(StrEnum):
    NONE = "NONE"
    TRANSIENT = "TRANSIENT"
    POLICY = "POLICY"
    PROVIDER = "PROVIDER"
    RESOURCE = "RESOURCE"
    LOGIC = "LOGIC"
    UNKNOWN = "UNKNOWN"


class CacheOutcome(StrEnum):
    HIT = "HIT"
    MISS = "MISS"


class MemoryKind(StrEnum):
    DECISION = "DECISION"
    FACT = "FACT"
    INCIDENT = "INCIDENT"
    LESSON = "LESSON"


class HealthLayerObservation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    observation_id: str
    layer: str
    state: LayerState
    reason: str
    recorded_at_utc: datetime
    evidence_ids: tuple[str, ...] = ()
    factors: tuple[str, ...] = ()
    superseded_by: str | None = None

    @field_validator("layer")
    @classmethod
    def validate_layer(cls, value: str) -> str:
        layer = value.strip().lower()
        if layer not in REQUIRED_HEALTH_LAYERS:
            raise ValueError(f"unsupported health layer: {value}")
        return layer


class WorkerRunRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str
    capability: str
    provider: str
    model_or_tool_version: str
    context_identity: str
    started_at_utc: datetime
    ended_at_utc: datetime
    duration_ms: int = Field(ge=0)
    cpu_ms: int = Field(ge=0)
    memory_bytes: int = Field(ge=0)
    usage: dict[str, int | float | str] = Field(default_factory=dict)
    result: WorkerResult
    failure_class: FailureClass = FailureClass.NONE
    recorded_at_utc: datetime


class CostSample(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    sample_id: str
    spend: float = Field(ge=0)
    quota: float = Field(ge=0)
    reserved_lease: float = Field(ge=0)
    forecast: float = Field(ge=0)
    local_resource_use: float = Field(ge=0)
    verified_outcome_cost: float = Field(ge=0)
    currency: str = "USD"
    recorded_at_utc: datetime


class CodeIndexEntry(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    path: str
    file_sha256: str
    imports: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    test_ids: tuple[str, ...] = ()
    last_commit_sha: str | None = None
    related_paths: tuple[str, ...] = ()

    @field_validator("file_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        digest = value.strip().lower()
        if not _DIGEST.fullmatch(digest):
            raise ValueError("file_sha256 must be a 64-character hex digest")
        return digest

    @field_validator("last_commit_sha")
    @classmethod
    def validate_sha(cls, value: str | None) -> str | None:
        if value is None:
            return None
        sha = value.strip().lower()
        if not _FULL_SHA.fullmatch(sha):
            raise ValueError("last_commit_sha must be a full 40-hex Git identity")
        return sha


class DependencyUpdateClass(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    package: str
    current_version: str
    proposed_version: str
    security_urgency: str
    compatibility_risk: str
    criticality: str
    required_verification: tuple[str, ...]
    create_work: bool


class CacheEvent(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: str
    cache_kind: str
    cache_identity: str
    outcome: CacheOutcome
    recorded_at_utc: datetime


class DistilledMemory(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    memory_id: str
    kind: MemoryKind
    statement: str
    citations: tuple[str, ...]
    verified: bool
    recorded_at_utc: datetime


class HealthFactor(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    layer: str
    state: LayerState
    stale: bool
    missing: bool
    contradictory: bool
    reason: str
    factors: tuple[str, ...] = ()


class HealthCalculation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    overall: LayerState
    as_of_utc: datetime
    freshness_seconds: int
    layers: tuple[HealthFactor, ...]
    user_action_required: Literal[False] = False
