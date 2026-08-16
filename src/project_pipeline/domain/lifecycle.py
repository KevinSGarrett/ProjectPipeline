from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field, model_validator


def lifecycle_identifier(prefix: str, *parts: str) -> str:
    material = "|".join([prefix, *parts]).encode("utf-8")
    return f"{prefix}-{sha256(material).hexdigest()[:12].upper()}"


class PortfolioMode(StrEnum):
    NORMAL = "NORMAL"
    BALANCED_PORTFOLIO = "BALANCED_PORTFOLIO"
    DEADLINE_SPRINT = "DEADLINE_SPRINT"
    EXCLUSIVE = "EXCLUSIVE"


class RepositoryRole(StrEnum):
    APPLICATION = "APPLICATION"
    FRONTEND = "FRONTEND"
    BACKEND = "BACKEND"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    SDK = "SDK"
    ML = "ML"
    DOCS = "DOCS"
    OTHER = "OTHER"


class EnvironmentType(StrEnum):
    LOCAL = "LOCAL"
    INTEGRATION = "INTEGRATION"
    PREVIEW = "PR_PREVIEW"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    TEMPORARY_TEST = "TEMPORARY_TEST"


class DataClassification(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    GOLDEN_FIXTURE = "GOLDEN_FIXTURE"
    SANITIZED_SNAPSHOT = "SANITIZED_SNAPSHOT"
    SENSITIVE_TEST = "SENSITIVE_TEST"
    PRODUCTION_DERIVED = "PRODUCTION_DERIVED"
    PRODUCTION = "PRODUCTION"


class ContractPhase(StrEnum):
    EXPAND = "EXPAND"
    MIGRATE = "MIGRATE"
    VERIFY = "VERIFY"
    CONTRACT = "CONTRACT"


class ProjectTerminalState(StrEnum):
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    CLOSING = "CLOSING"
    ARCHIVED = "ARCHIVED"
    DECOMMISSIONED = "DECOMMISSIONED"


class QualificationState(StrEnum):
    QUALIFICATION = "QUALIFICATION"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DEPRECATED = "DEPRECATED"
    DISABLED = "DISABLED"
    RETIRED = "RETIRED"


class ProjectPortfolioRegistration(BaseModel):
    project_id: str
    authority_id: str
    priority: int = Field(ge=0, le=100)
    deadline_at_utc: datetime | None = None
    guaranteed_worker_slots: int = Field(default=1, ge=0)
    max_worker_share_percent: int = Field(default=100, ge=1, le=100)
    budget_weight: int = Field(default=1, ge=1)
    operator_importance: int = Field(default=50, ge=0, le=100)
    starvation_age_seconds: int = Field(default=0, ge=0)
    credential_scope_id: str
    context_scope_id: str
    permission_scope_id: str


class RepositoryBinding(BaseModel):
    repository_id: str
    canonical_url: str
    role: RepositoryRole
    steward_id: str
    revision: str
    dependencies: tuple[str, ...] = ()


class CrossRepositoryChangeSet(BaseModel):
    change_set_id: str
    project_id: str
    requirement_ids: tuple[str, ...]
    repository_changes: dict[str, str]
    merge_order: tuple[str, ...]
    shared_change_identity: str

    @model_validator(mode="after")
    def validate_order(self) -> CrossRepositoryChangeSet:
        keys = set(self.repository_changes)
        if set(self.merge_order) != keys:
            raise ValueError("merge_order must cover repository_changes exactly")
        return self


class EnvironmentLease(BaseModel):
    environment_id: str
    project_id: str
    environment_type: EnvironmentType
    owner_id: str
    revision: str
    namespace: str
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int | None = Field(default=None, ge=1)
    data_classification: DataClassification
    seed_version: str | None = None
    production_copy_explicitly_permitted: bool = False
    transformation_verified: bool = False


class TestDataAsset(BaseModel):
    asset_id: str
    project_id: str
    classification: DataClassification
    provenance: str
    access_policy_id: str
    refresh_policy: str
    retention_days: int = Field(ge=0)
    destruction_mode: str
    masking_verified: bool = False


class ContractEvolution(BaseModel):
    evolution_id: str
    contract_id: str
    from_version: str
    to_version: str
    phase: ContractPhase
    compatible_consumers: tuple[str, ...] = ()
    incompatible_consumers: tuple[str, ...] = ()
    migration_plan_id: str
    rollback_plan_id: str
    verification_evidence_ids: tuple[str, ...] = ()


class RetentionPolicy(BaseModel):
    class_id: str
    retention_days: int | None = Field(default=None, ge=0)
    permanent: bool = False
    secure_delete_required: bool = False
    legal_hold_blocks_deletion: bool = True

    @model_validator(mode="after")
    def finite_or_permanent(self) -> RetentionPolicy:
        if not self.permanent and self.retention_days is None:
            raise ValueError("retention_days required unless permanent")
        return self


class VersionQualification(BaseModel):
    qualification_id: str
    subject_kind: str
    subject_id: str
    version: str
    state: QualificationState
    detected_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    compatibility_profile: str
    evidence_ids: tuple[str, ...] = ()
    high_risk_routing_allowed: bool = False


class PlatformReleaseCandidate(BaseModel):
    release_id: str
    artifact_sha256: str
    platform_version: str
    schema_version: str
    adapter_versions: dict[str, str]
    policy_version: str
    profile_version: str
    migration_plan_id: str
    rollback_plan_id: str
    synthetic_e2e_certification_evidence_ids: tuple[str, ...] = ()
    canary_or_shadow_evidence_ids: tuple[str, ...] = ()
    post_upgrade_verification_plan_id: str


class ClosureReadiness(BaseModel):
    project_id: str
    current_state: ProjectTerminalState
    final_requirements_verified: bool = False
    final_release_signed: bool = False
    jira_reconciled: bool = False
    git_clean: bool = False
    evidence_archive_built: bool = False
    jira_snapshot_built: bool = False
    handoff_built: bool = False
    unused_resources_release_planned: bool = False
    credentials_revocation_planned: bool = False
    scheduled_tasks_disable_planned: bool = False
    final_backup_restore_verified: bool = False
    legal_hold_active: bool = False


class AdoptionMaturity(BaseModel):
    project_id: str
    discovery_complete: bool
    baseline_captured: bool
    gap_analysis_complete: bool
    adoption_plan_approved: bool
    controlled_bootstrap_complete: bool
    shadow_autonomy_verified: bool
    limited_autonomy_verified: bool
    full_autonomy_eligible: bool
    authoritative_assets_mutated_by_assessment: bool = False

    @property
    def score(self) -> int:
        flags = [
            self.discovery_complete,
            self.baseline_captured,
            self.gap_analysis_complete,
            self.adoption_plan_approved,
            self.controlled_bootstrap_complete,
            self.shadow_autonomy_verified,
            self.limited_autonomy_verified,
            self.full_autonomy_eligible,
        ]
        return round(100 * sum(flags) / len(flags))

    def model_dump_with_score(self) -> dict[str, Any]:
        return {**self.model_dump(mode="json"), "maturity_score": self.score}
