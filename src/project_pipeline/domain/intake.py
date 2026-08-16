from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.domain.identifiers import (
    IdentifierKind,
    deterministic_identifier,
    project_identifier,
    validate_identifier,
)
from project_pipeline.domain.project import ProjectOrigin, RepositoryRole


class IntakeMode(StrEnum):
    NEW_PROJECT = "NEW_PROJECT"
    EXISTING_PROJECT = "EXISTING_PROJECT"


class AdoptionStage(StrEnum):
    DISCOVERY = "DISCOVERY"
    BASELINE = "BASELINE"
    GAP_ANALYSIS = "GAP_ANALYSIS"
    ADOPTION_PLAN = "ADOPTION_PLAN"
    CONTROLLED_BOOTSTRAP = "CONTROLLED_BOOTSTRAP"
    SHADOW_AUTONOMY = "SHADOW_AUTONOMY"
    LIMITED_AUTONOMY = "LIMITED_AUTONOMY"
    FULL_AUTONOMY = "FULL_AUTONOMY"


class ProjectScale(StrEnum):
    SMALL = "SMALL"
    STANDARD = "STANDARD"
    LARGE = "LARGE"
    CRITICAL = "CRITICAL"


class ProjectProfile(StrEnum):
    GENERIC = "GENERIC"
    PYTHON_LIBRARY = "PYTHON_LIBRARY"
    PYTHON_SERVICE = "PYTHON_SERVICE"
    WEB_APPLICATION = "WEB_APPLICATION"
    TYPESCRIPT_APPLICATION = "TYPESCRIPT_APPLICATION"
    RUST_APPLICATION = "RUST_APPLICATION"
    MACHINE_LEARNING = "MACHINE_LEARNING"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    DOCUMENTATION = "DOCUMENTATION"
    POLYGLOT_APPLICATION = "POLYGLOT_APPLICATION"
    EMPTY = "EMPTY"


class DiscoveryArtifactKind(StrEnum):
    SOURCE = "SOURCE"
    TEST = "TEST"
    INSTRUCTION = "INSTRUCTION"
    PLAN = "PLAN"
    JIRA = "JIRA"
    REQUIREMENT = "REQUIREMENT"
    EVIDENCE = "EVIDENCE"
    CONFIGURATION = "CONFIGURATION"
    BUILD = "BUILD"
    CI = "CI"
    DEPLOYMENT = "DEPLOYMENT"
    DOCUMENTATION = "DOCUMENTATION"
    SECRET_REFERENCE = "SECRET_REFERENCE"
    REPOSITORY_METADATA = "REPOSITORY_METADATA"
    OTHER = "OTHER"


class DiscoveryTrust(StrEnum):
    UNTRUSTED_DISCOVERED = "UNTRUSTED_DISCOVERED"
    SOURCE_CONTROLLED_DECLARATION = "SOURCE_CONTROLLED_DECLARATION"


class VersionControlKind(StrEnum):
    GIT = "GIT"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class GapCategory(StrEnum):
    AUTHORITY = "AUTHORITY"
    BOUNDARY = "BOUNDARY"
    DOCUMENTATION = "DOCUMENTATION"
    GOVERNANCE = "GOVERNANCE"
    INSTRUCTIONS = "INSTRUCTIONS"
    PLANNING = "PLANNING"
    REQUIREMENTS = "REQUIREMENTS"
    TESTING = "TESTING"
    CI = "CI"
    DEPLOYMENT = "DEPLOYMENT"
    SECURITY = "SECURITY"
    BUILD = "BUILD"
    PERSISTENCE = "PERSISTENCE"
    PROFILE = "PROFILE"


class GapSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BootstrapActionKind(StrEnum):
    CREATE_DIRECTORY = "CREATE_DIRECTORY"
    CREATE_FILE = "CREATE_FILE"
    SATISFIED = "SATISFIED"
    CONFLICT = "CONFLICT"


class BootstrapOutcome(StrEnum):
    DRY_RUN = "DRY_RUN"
    APPLIED = "APPLIED"
    NO_CHANGES = "NO_CHANGES"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


def _validate_relative_path(value: str, *, allow_dot: bool = False) -> str:
    if not value or value.strip() != value:
        raise ValueError("path must be non-empty and trimmed")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path must be repository-relative and cannot traverse upward")
    if not allow_dot and normalized in {".", ""}:
        raise ValueError("path cannot be the repository root")
    if any(part in {"", "."} for part in path.parts if part != "."):
        raise ValueError("path contains an invalid segment")
    return normalized


def _stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


class DiscoveredFile(DomainModel):
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    suffix: str = Field(default="", max_length=32)
    language: str | None = Field(default=None, max_length=64)
    role: DiscoveryArtifactKind = DiscoveryArtifactKind.OTHER
    trust: DiscoveryTrust = DiscoveryTrust.UNTRUSTED_DISCOVERED
    symbols: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    tested_by: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    change_relevance: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator(
        "symbols", "dependencies", "tested_by", "owners", "change_relevance", "diagnostics"
    )
    @classmethod
    def reject_duplicates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("discovery lists cannot contain duplicates")
        return values


class DiscoveredSymlink(DomainModel):
    path: str
    target: str
    target_within_root: bool
    traversed: Literal[False] = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class RepositoryIdentity(DomainModel):
    repository_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    root_path: str
    role: RepositoryRole = RepositoryRole.PRIMARY
    version_control: VersionControlKind = VersionControlKind.NONE
    canonical_url: str | None = Field(default=None, max_length=2048)
    default_branch: str | None = Field(default=None, max_length=255)
    head_revision: str | None = Field(default=None, max_length=128)
    nested: bool = False

    @field_validator("root_path")
    @classmethod
    def validate_root_path(cls, value: str) -> str:
        return _validate_relative_path(value, allow_dot=True)


class RepositoryDiscovery(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    root_path: str
    repositories: tuple[RepositoryIdentity, ...]
    files: tuple[DiscoveredFile, ...]
    symlinks: tuple[DiscoveredSymlink, ...] = ()
    instruction_paths: tuple[str, ...] = ()
    plan_paths: tuple[str, ...] = ()
    jira_paths: tuple[str, ...] = ()
    requirement_paths: tuple[str, ...] = ()
    evidence_paths: tuple[str, ...] = ()
    build_systems: tuple[str, ...] = ()
    test_commands: tuple[str, ...] = ()
    deployment_surfaces: tuple[str, ...] = ()
    secret_reference_count: int = Field(default=0, ge=0)
    boundary_violations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    total_bytes: int = Field(ge=0)
    truncated: bool = False

    @field_validator(
        "instruction_paths",
        "plan_paths",
        "jira_paths",
        "requirement_paths",
        "evidence_paths",
        "build_systems",
        "test_commands",
        "deployment_surfaces",
        "boundary_violations",
        "diagnostics",
    )
    @classmethod
    def reject_duplicates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("discovery summary lists cannot contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_primary_repository(self) -> RepositoryDiscovery:
        if not self.repositories:
            raise ValueError("discovery requires a primary repository identity")
        if sum(item.role is RepositoryRole.PRIMARY for item in self.repositories) != 1:
            raise ValueError("discovery requires exactly one primary repository")
        return self

    def semantic_fingerprint(self) -> str:
        return _stable_digest(self.model_dump(mode="json"))


class RepositoryMapEntry(DomainModel):
    path: str
    role: DiscoveryArtifactKind
    language: str | None = None
    size_bytes: int = Field(ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    symbols: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    tested_by: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    change_relevance: tuple[str, ...] = ()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class CompiledRepositoryMap(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    root_path: str
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    top_level_counts: dict[str, int]
    language_counts: dict[str, int]
    role_counts: dict[str, int]
    entries: tuple[RepositoryMapEntry, ...]

    @model_validator(mode="after")
    def validate_counts(self) -> CompiledRepositoryMap:
        if self.file_count != len(self.entries):
            raise ValueError("repository map file_count differs from entries")
        if sum(self.top_level_counts.values()) != self.file_count:
            raise ValueError("repository map top-level counts do not sum to file_count")
        expected = _stable_digest([entry.model_dump(mode="json") for entry in self.entries])
        if expected != self.fingerprint:
            raise ValueError("repository map fingerprint differs from entries")
        return self


class ProjectProfileDetection(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    primary_profile: ProjectProfile
    profiles: tuple[ProjectProfile, ...]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, tuple[str, ...]]
    policy_activations: tuple[str, ...]

    @model_validator(mode="after")
    def validate_profiles(self) -> ProjectProfileDetection:
        if self.primary_profile not in self.profiles:
            raise ValueError("primary profile must be included in profiles")
        if len(self.profiles) != len(set(self.profiles)):
            raise ValueError("profiles cannot contain duplicates")
        return self


class ProjectGap(DomainModel):
    gap_id: str = Field(pattern=r"^GAP-[A-F0-9]{20}$")
    category: GapCategory
    severity: GapSeverity
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=4000)
    affected_paths: tuple[str, ...] = ()
    remediation: str = Field(min_length=1, max_length=4000)
    blocks_autonomy: bool = False
    bootstrap_eligible: bool = False

    @classmethod
    def create(
        cls,
        *,
        category: GapCategory,
        severity: GapSeverity,
        title: str,
        description: str,
        remediation: str,
        affected_paths: tuple[str, ...] = (),
        blocks_autonomy: bool = False,
        bootstrap_eligible: bool = False,
    ) -> ProjectGap:
        identity = deterministic_identifier(
            IdentifierKind.GAP,
            category.value,
            severity.value,
            title,
            "\x1e".join(sorted(affected_paths)) or "NO_AFFECTED_PATHS",
        )
        return cls(
            gap_id=str(identity),
            category=category,
            severity=severity,
            title=title,
            description=description,
            remediation=remediation,
            affected_paths=tuple(sorted(affected_paths)),
            blocks_autonomy=blocks_autonomy,
            bootstrap_eligible=bootstrap_eligible,
        )


class ProjectGapReport(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    gaps: tuple[ProjectGap, ...]
    counts_by_severity: dict[str, int]
    blocks_autonomy: bool
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> ProjectGapReport:
        expected = _stable_digest([item.model_dump(mode="json") for item in self.gaps])
        if self.fingerprint != expected:
            raise ValueError("gap report fingerprint differs from gaps")
        if self.blocks_autonomy != any(item.blocks_autonomy for item in self.gaps):
            raise ValueError("gap report autonomy state differs from gaps")
        return self


class ProjectIntakeRequest(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    mode: IntakeMode
    project_name: str = Field(min_length=1, max_length=512)
    project_id: str | None = None
    target_root: str = Field(min_length=1, max_length=4096)
    scale: ProjectScale = ProjectScale.STANDARD
    requested_profiles: tuple[ProjectProfile, ...] = ()
    canonical_url: str | None = Field(default=None, max_length=2048)
    allow_nested_repositories: bool = False
    max_files: int = Field(default=20_000, ge=1, le=1_000_000)
    max_total_bytes: int = Field(default=2_000_000_000, ge=1, le=10_000_000_000_000)
    max_hash_bytes_per_file: int = Field(default=16_000_000, ge=1, le=1_000_000_000)
    actor_id: str = Field(default="actor:local-intake", min_length=3, max_length=255)
    correlation_id: str = Field(default="corr:local-intake", min_length=3, max_length=255)

    @field_validator("project_name", "target_root", "actor_id", "correlation_id")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("intake text values cannot be blank")
        if any(character in value for character in ("\x00", "\n", "\r")):
            raise ValueError("intake text contains an invalid character")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str | None) -> str | None:
        return None if value is None else validate_identifier(value, IdentifierKind.PROJECT)

    @field_validator("requested_profiles")
    @classmethod
    def validate_requested_profiles(
        cls, values: tuple[ProjectProfile, ...]
    ) -> tuple[ProjectProfile, ...]:
        if len(values) != len(set(values)):
            raise ValueError("requested profiles cannot contain duplicates")
        return values

    def resolved_project_id(self) -> str:
        return self.project_id or str(project_identifier(self.project_name))

    def semantic_fingerprint(self) -> str:
        return _stable_digest(self.model_dump(mode="json"))


class CompiledProjectManifest(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    compilation_id: str
    project_id: str
    project_name: str
    origin: ProjectOrigin
    intake_mode: IntakeMode
    adoption_stage: AdoptionStage
    target_root: str
    scale: ProjectScale
    primary_profile: ProjectProfile
    profiles: tuple[ProjectProfile, ...]
    repositories: tuple[RepositoryIdentity, ...]
    instruction_paths: tuple[str, ...]
    plan_paths: tuple[str, ...]
    jira_paths: tuple[str, ...]
    requirement_paths: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    build_systems: tuple[str, ...]
    test_commands: tuple[str, ...]
    deployment_surfaces: tuple[str, ...]
    operating_constraints: tuple[str, ...]
    source_authorities: tuple[str, ...]
    repository_map: CompiledRepositoryMap
    gap_report: ProjectGapReport
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    compiled_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("compilation_id")
    @classmethod
    def validate_compilation_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.COMPILATION)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @field_validator("compiled_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("compilation timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_manifest(self) -> CompiledProjectManifest:
        if self.primary_profile not in self.profiles:
            raise ValueError("primary profile must be present in profiles")
        expected = deterministic_identifier(
            IdentifierKind.COMPILATION,
            self.project_id,
            self.request_fingerprint,
            self.repository_map.fingerprint,
            self.gap_report.fingerprint,
            self.primary_profile.value,
        )
        if self.compilation_id != str(expected):
            raise ValueError("compilation identity differs from semantic inputs")
        return self

    def semantic_fingerprint(self) -> str:
        return _stable_digest(self.model_dump(mode="json", exclude={"compiled_at_utc"}))


class BootstrapAction(DomainModel):
    path: str
    action: BootstrapActionKind
    reason: str = Field(min_length=1, max_length=1000)
    content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class BootstrapPlan(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    bootstrap_id: str
    compilation_id: str
    project_id: str
    intake_mode: IntakeMode
    target_root: str
    actions: tuple[BootstrapAction, ...]
    requires_existing_project_confirmation: bool
    destructive_actions: Literal[False] = False
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("bootstrap_id")
    @classmethod
    def validate_bootstrap_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.BOOTSTRAP)

    @field_validator("compilation_id")
    @classmethod
    def validate_compilation_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.COMPILATION)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @model_validator(mode="after")
    def validate_plan(self) -> BootstrapPlan:
        expected_fingerprint = _stable_digest(
            [item.model_dump(mode="json") for item in self.actions]
        )
        if expected_fingerprint != self.fingerprint:
            raise ValueError("bootstrap fingerprint differs from actions")
        expected_id = deterministic_identifier(
            IdentifierKind.BOOTSTRAP,
            self.compilation_id,
            self.target_root,
            self.fingerprint,
        )
        if self.bootstrap_id != str(expected_id):
            raise ValueError("bootstrap identity differs from semantic inputs")
        return self


class BootstrapReceipt(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    bootstrap_id: str
    compilation_id: str
    outcome: BootstrapOutcome
    target_root: str
    created_paths: tuple[str, ...] = ()
    satisfied_paths: tuple[str, ...] = ()
    conflict_paths: tuple[str, ...] = ()
    rolled_back_paths: tuple[str, ...] = ()
    actor_id: str
    correlation_id: str
    recorded_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("bootstrap_id")
    @classmethod
    def validate_bootstrap_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.BOOTSTRAP)

    @field_validator("compilation_id")
    @classmethod
    def validate_compilation_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.COMPILATION)

    @field_validator("recorded_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bootstrap receipt timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_outcome(self) -> BootstrapReceipt:
        if (
            self.outcome in {BootstrapOutcome.APPLIED, BootstrapOutcome.NO_CHANGES}
            and self.conflict_paths
        ):
            raise ValueError("successful bootstrap receipt cannot include conflicts")
        if self.outcome is BootstrapOutcome.DRY_RUN and (
            self.created_paths or self.rolled_back_paths
        ):
            raise ValueError("dry-run receipt cannot report created or rolled-back paths")
        return self
