from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now

OBSERVATION_ID = re.compile(r"^OBSV-[A-F0-9]{20}$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


def observation_identifier(*parts: str) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("observation identifier parts must be non-empty")
    payload = "\x1f".join(str(part).strip() for part in parts)
    return f"OBSV-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def canonical_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ObservationResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class EnvironmentClass(StrEnum):
    LOCAL = "LOCAL"
    CI = "CI"
    WINDOWS_NATIVE = "WINDOWS_NATIVE"
    LIVE = "LIVE"
    MOCK = "MOCK"


class MergeKind(StrEnum):
    NONE = "NONE"
    SQUASH = "SQUASH"
    MERGE = "MERGE"
    REBASE = "REBASE"


class EvidenceDefinition(DomainModel):
    """Source-controlled evidence row. It is a definition, not a current-head proof."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    evidence_id: str
    claim: str
    criterion_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    artifact_path: str
    sha256: str
    method: str
    environment: str
    policy: str = "default"
    test_ids: tuple[str, ...] = ()

    @field_validator("sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        digest = value.strip().lower()
        if not _DIGEST.fullmatch(digest):
            raise ValueError("evidence definition digest must be a 64-character hex SHA-256")
        return digest


class MetadataOnlyDiffProof(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    from_sha: str
    to_sha: str
    from_tree: str
    to_tree: str
    changed_paths: tuple[str, ...]
    allowlisted: bool
    acceptance_scope_unchanged: bool
    reason: str

    @field_validator("from_sha", "to_sha", "from_tree", "to_tree")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        digest = value.strip().lower()
        if not _FULL_SHA.fullmatch(digest):
            raise ValueError("metadata-only proof requires full Git object ids")
        return digest


class EvidenceObservation(DomainModel):
    """Immutable execution receipt bound to an exact subject commit/tree."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    observation_id: str
    evidence_id: str
    test_ids: tuple[str, ...]
    criterion_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    integrated_sha: str
    integrated_tree: str
    acceptance_scope_fingerprint: str
    path_fingerprints: dict[str, str] = Field(default_factory=dict)
    requirement_scope_fingerprints: dict[str, str] = Field(default_factory=dict)
    test_outcomes: dict[str, str] = Field(default_factory=dict)
    artifact_digest: str
    command_identity: tuple[str, ...]
    environment_class: EnvironmentClass
    recorded_at_utc: datetime = Field(default_factory=utc_now)
    result: ObservationResult
    verification_status: Literal["VERIFIED", "UNVERIFIED"] = "UNVERIFIED"
    independent_verification_receipt: str = ""
    branch_head_sha: str | None = None
    merge_kind: MergeKind = MergeKind.NONE
    metadata_only_diff_proof: MetadataOnlyDiffProof | None = None
    supersedes: str | None = None
    provenance: str | None = None

    @field_validator("observation_id")
    @classmethod
    def validate_observation_id(cls, value: str) -> str:
        if not OBSERVATION_ID.fullmatch(value):
            raise ValueError(f"invalid observation identifier: {value}")
        return value

    @field_validator("integrated_sha", "integrated_tree")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        digest = value.strip().lower()
        if not _FULL_SHA.fullmatch(digest):
            raise ValueError("observation subject must be a full 40-character Git object id")
        return digest

    @field_validator("acceptance_scope_fingerprint", "artifact_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        digest = value.strip().lower()
        if not _DIGEST.fullmatch(digest):
            raise ValueError("observation digest must be a 64-character hex SHA-256")
        return digest

    @field_validator("branch_head_sha")
    @classmethod
    def validate_branch_head(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        digest = value.strip().lower()
        if not _FULL_SHA.fullmatch(digest):
            raise ValueError("branch head SHA must be a full Git object id")
        return digest

    @field_validator("recorded_at_utc")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_semantics(self) -> EvidenceObservation:
        if not self.command_identity:
            raise ValueError("observation requires a command identity")
        if (
            self.environment_class is EnvironmentClass.MOCK
            and self.result is ObservationResult.PASS
        ):
            raise ValueError("mock observations cannot prove passing acceptance")
        if self.supersedes and self.supersedes == self.observation_id:
            raise ValueError("observation cannot supersede itself")
        return self
