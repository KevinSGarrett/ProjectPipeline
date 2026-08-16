from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now

_ID = re.compile(r"^[A-Z][A-Z0-9-]*-[A-F0-9]{20}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _digest(prefix: str, *parts: str) -> str:
    if not parts or any(not p.strip() for p in parts):
        raise ValueError("digest identifier parts must be non-empty")
    raw = "\x1f".join(p.strip() for p in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:20].upper()}"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


class ContextSourceKind(StrEnum):
    SOURCE = "SOURCE"
    REQUIREMENT = "REQUIREMENT"
    PLAN = "PLAN"
    JIRA = "JIRA"
    DECISION = "DECISION"
    EVIDENCE = "EVIDENCE"
    POLICY = "POLICY"
    INSTRUCTION = "INSTRUCTION"
    REPOSITORY_MAP = "REPOSITORY_MAP"
    SOURCE_FILE = "SOURCE_FILE"
    TEST = "TEST"
    DIFF = "DIFF"
    REVIEW_RUBRIC = "REVIEW_RUBRIC"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class ContextTrust(StrEnum):
    GOVERNING = "GOVERNING"
    AUTHORITATIVE = "AUTHORITATIVE"
    SOURCE_CONTROLLED = "SOURCE_CONTROLLED"
    VERIFIED_EXTERNAL = "VERIFIED_EXTERNAL"
    UNTRUSTED_REPOSITORY = "UNTRUSTED_REPOSITORY"
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"


class Sensitivity(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3
    SECRET = 4


class ProviderEgress(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    HOSTED_ALLOWED = "HOSTED_ALLOWED"


class FreshnessStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ReceiptStatus(StrEnum):
    CONSUMED = "CONSUMED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"


class DelegationEnvelope(DomainModel):
    delegation_id: str
    objective: str = Field(min_length=1, max_length=4000)
    scope: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    authority_scope: tuple[str, ...] = ()
    resource_requirements: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    return_protocol: str = Field(min_length=1, max_length=2000)
    required_context_keys: tuple[str, ...] = ()
    optional_context_keys: tuple[str, ...] = ()
    expected_revisions: dict[str, str] = Field(default_factory=dict)

    @field_validator("delegation_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value.startswith("DELEG-") or not _ID.fullmatch(value):
            raise ValueError("invalid delegation identifier")
        return value

    @field_validator(
        "scope",
        "exclusions",
        "constraints",
        "source_references",
        "expected_outputs",
        "acceptance_criteria",
        "authority_scope",
        "resource_requirements",
        "allowed_tools",
        "required_context_keys",
        "optional_context_keys",
    )
    @classmethod
    def unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(v.strip() for v in values)
        if any(not v for v in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("delegation tuple values must be non-empty and unique")
        return cleaned

    @model_validator(mode="after")
    def validate_context_keys(self) -> DelegationEnvelope:
        if set(self.required_context_keys) & set(self.optional_context_keys):
            raise ValueError("context key cannot be both required and optional")
        unknown = (
            set(self.expected_revisions)
            - set(self.required_context_keys)
            - set(self.optional_context_keys)
        )
        if unknown:
            raise ValueError(
                f"expected revisions reference unknown context keys: {sorted(unknown)}"
            )
        return self

    @classmethod
    def create(cls, *, objective: str, return_protocol: str, **kwargs: Any) -> DelegationEnvelope:
        body = {"objective": objective, "return_protocol": return_protocol, **kwargs}
        identifier = _digest("DELEG", hashlib.sha256(_canonical(body)).hexdigest())
        return cls(delegation_id=identifier, **body)


class ContextCandidate(DomainModel):
    context_key: str = Field(min_length=1, max_length=500)
    kind: ContextSourceKind
    content: str
    revision_id: str = Field(min_length=1, max_length=300)
    observed_at_utc: datetime
    trust: ContextTrust
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    source_reference: str | None = Field(default=None, max_length=1000)
    relevance_tags: tuple[str, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("context_key", "revision_id")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("context keys and revisions must be trimmed")
        return value


class ContextPolicy(DomainModel):
    policy_version: str = Field(pattern=r"^CTX-POLICY-[0-9]+(?:\.[0-9]+)*$")
    max_items: int = Field(default=64, ge=1, le=5000)
    max_chars: int = Field(default=200_000, ge=1024, le=50_000_000)
    max_age_seconds: int = Field(default=86_400, ge=1)
    hosted_max_sensitivity: Sensitivity = Sensitivity.INTERNAL
    allow_stale_optional: bool = False
    allow_untrusted_data: bool = True
    allow_untrusted_instructions: bool = False
    redact_secrets: bool = True
    min_coverage_score: float = Field(default=1.0, ge=0.0, le=1.0)


class ContextSelection(DomainModel):
    delegation_id: str
    selected_keys: tuple[str, ...]
    omitted_keys: tuple[str, ...] = ()
    unknown_keys: tuple[str, ...] = ()
    selection_reason: tuple[str, ...] = ()


class FirewallResult(DomainModel):
    context_key: str
    allowed: bool
    content: str
    reasons: tuple[str, ...] = ()
    redaction_count: int = Field(default=0, ge=0)
    trust: ContextTrust
    sensitivity: Sensitivity


class ContextItem(DomainModel):
    item_id: str
    context_key: str
    kind: ContextSourceKind
    content: str
    revision_id: str
    trust: ContextTrust
    sensitivity: Sensitivity
    source_reference: str | None = None
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("item_id")
    @classmethod
    def valid_item_id(cls, value: str) -> str:
        if not value.startswith("CTXITEM-") or not _ID.fullmatch(value):
            raise ValueError("invalid context item id")
        return value

    @classmethod
    def from_candidate(cls, candidate: ContextCandidate, *, content: str) -> ContextItem:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(
            item_id=_digest("CTXITEM", candidate.context_key, candidate.revision_id, digest),
            context_key=candidate.context_key,
            kind=candidate.kind,
            content=content,
            revision_id=candidate.revision_id,
            trust=candidate.trust,
            sensitivity=candidate.sensitivity,
            source_reference=candidate.source_reference,
            content_sha256=digest,
        )


class CoverageReport(DomainModel):
    required_count: int = Field(ge=0)
    represented_count: int = Field(ge=0)
    missing_keys: tuple[str, ...] = ()
    score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def consistent(self) -> CoverageReport:
        if self.represented_count > self.required_count:
            raise ValueError("represented count exceeds required count")
        expected = 1.0 if self.required_count == 0 else self.represented_count / self.required_count
        if abs(self.score - expected) > 1e-9:
            raise ValueError("coverage score is inconsistent")
        return self


class ContextPack(DomainModel):
    pack_id: str
    delegation_id: str
    policy_version: str
    generated_at_utc: datetime
    items: tuple[ContextItem, ...]
    coverage: CoverageReport
    stale_keys: tuple[str, ...] = ()
    redaction_count: int = Field(default=0, ge=0)
    omissions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    total_chars: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("pack_id")
    @classmethod
    def valid_pack_id(cls, value: str) -> str:
        if not value.startswith("CTXPACK-") or not _ID.fullmatch(value):
            raise ValueError("invalid context pack id")
        return value

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "policy_version": self.policy_version,
            "items": [i.model_dump(mode="json") for i in self.items],
            "coverage": self.coverage.model_dump(mode="json"),
            "stale_keys": list(self.stale_keys),
            "redaction_count": self.redaction_count,
            "omissions": list(self.omissions),
            "warnings": list(self.warnings),
            "total_chars": self.total_chars,
        }


class ContextReceipt(DomainModel):
    receipt_id: str
    pack_id: str
    worker_id: str = Field(min_length=1, max_length=300)
    consumed_at_utc: datetime
    status: ReceiptStatus
    omissions_detected: tuple[str, ...] = ()
    conflicts_encountered: tuple[str, ...] = ()
    additional_context_requested: tuple[str, ...] = ()

    @field_validator("receipt_id")
    @classmethod
    def valid_receipt_id(cls, value: str) -> str:
        if not value.startswith("CTXREC-") or not _ID.fullmatch(value):
            raise ValueError("invalid context receipt id")
        return value

    @classmethod
    def create(
        cls,
        *,
        pack_id: str,
        worker_id: str,
        status: ReceiptStatus,
        omissions_detected: tuple[str, ...] = (),
        conflicts_encountered: tuple[str, ...] = (),
        additional_context_requested: tuple[str, ...] = (),
        consumed_at_utc: datetime | None = None,
    ) -> ContextReceipt:
        consumed = consumed_at_utc or utc_now()
        rid = _digest(
            "CTXREC",
            pack_id,
            worker_id,
            status.value,
            consumed.isoformat(),
            "|".join(omissions_detected) or "NONE",
            "|".join(conflicts_encountered) or "NONE",
            "|".join(additional_context_requested) or "NONE",
        )
        return cls(
            receipt_id=rid,
            pack_id=pack_id,
            worker_id=worker_id,
            consumed_at_utc=consumed,
            status=status,
            omissions_detected=omissions_detected,
            conflicts_encountered=conflicts_encountered,
            additional_context_requested=additional_context_requested,
        )


class ContextTelemetry(DomainModel):
    pack_id: str
    item_count: int = Field(ge=0)
    total_chars: int = Field(ge=0)
    source_count: int = Field(ge=0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    trust_counts: dict[str, int]
    stale_count: int = Field(ge=0)
    redaction_count: int = Field(ge=0)
    omission_count: int = Field(ge=0)
    receipt_status: ReceiptStatus | None = None


class ReviewerPackage(DomainModel):
    review_package_id: str
    context_pack_id: str
    diff_keys: tuple[str, ...]
    source_keys: tuple[str, ...]
    test_keys: tuple[str, ...]
    evidence_keys: tuple[str, ...]
    rubric_keys: tuple[str, ...]

    @field_validator("review_package_id")
    @classmethod
    def valid_review_id(cls, value: str) -> str:
        if not value.startswith("CTXREVIEW-") or not _ID.fullmatch(value):
            raise ValueError("invalid review package id")
        return value
