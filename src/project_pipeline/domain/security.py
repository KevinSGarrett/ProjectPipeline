from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now

SECURITY_ID = re.compile(
    r"^(IDENT|ROLE|GRANT|APPROVAL|POLICY|EGRESS|SREF|SLEASE|SAUDIT|SBOM|SCOMP|PROV|INTEGRITY|SCANEVID|SGATE|SELFCHG|ROOTTRUST)-[A-F0-9]{20}$"
)


def security_identifier(prefix: str, *parts: str) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("security identifier parts must be non-empty")
    payload = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def security_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class IdentityKind(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SERVICE = "SERVICE"
    ADAPTER = "ADAPTER"


class IdentityState(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class AuthorityCapability(StrEnum):
    READ = "READ"
    PROPOSE = "PROPOSE"
    APPROVE = "APPROVE"
    MUTATE = "MUTATE"
    MERGE = "MERGE"
    DEPLOY = "DEPLOY"
    SPEND = "SPEND"
    EXTERNAL_MODEL = "EXTERNAL_MODEL"
    ACCESS_SECRET = "ACCESS_SECRET"
    MODIFY_INSTRUCTIONS = "MODIFY_INSTRUCTIONS"
    MODIFY_POLICY = "MODIFY_POLICY"
    COMPLETE_PROJECT = "COMPLETE_PROJECT"
    EMERGENCY = "EMERGENCY"


class ApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class PolicyDisposition(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    CONSTRAIN = "CONSTRAIN"


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"
    LOCAL_ONLY = "LOCAL_ONLY"


class SecretBackendKind(StrEnum):
    ENVIRONMENT = "ENVIRONMENT"
    FILE = "FILE"
    SOPS = "SOPS"
    AGE = "AGE"
    OPENBAO = "OPENBAO"


class SupplyChainSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SupplyChainFindingKind(StrEnum):
    SECRET = "SECRET"
    VULNERABILITY = "VULNERABILITY"
    MISCONFIGURATION = "MISCONFIGURATION"
    LICENSE = "LICENSE"
    PROVENANCE = "PROVENANCE"
    INTEGRITY = "INTEGRITY"
    CI_PERMISSION = "CI_PERMISSION"
    ACTION_PINNING = "ACTION_PINNING"
    SBOM = "SBOM"
    SIGNATURE = "SIGNATURE"


class GateState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class SecurityIdentity(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    identity_id: str
    kind: IdentityKind
    display_name: str = Field(min_length=1, max_length=200)
    principal: str = Field(min_length=1, max_length=512)
    state: IdentityState = IdentityState.ACTIVE
    project_ids: tuple[str, ...] = ()
    environment_scopes: tuple[str, ...] = ()
    role_ids: tuple[str, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("created_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_identity(self) -> SecurityIdentity:
        if not SECURITY_ID.fullmatch(self.identity_id) or not self.identity_id.startswith("IDENT-"):
            raise ValueError("invalid security identity id")
        return self


class RoleDefinition(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    role_id: str
    name: str = Field(min_length=2, max_length=100)
    capabilities: tuple[AuthorityCapability, ...]
    allowed_target_prefixes: tuple[str, ...] = ()
    allowed_environments: tuple[str, ...] = ()
    max_risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    emergency: bool = False

    @model_validator(mode="after")
    def validate_role(self) -> RoleDefinition:
        if not SECURITY_ID.fullmatch(self.role_id) or not self.role_id.startswith("ROLE-"):
            raise ValueError("invalid role id")
        if not self.capabilities:
            raise ValueError("role requires at least one capability")
        if self.emergency and AuthorityCapability.EMERGENCY not in self.capabilities:
            raise ValueError("emergency role requires EMERGENCY capability")
        return self


class CapabilityGrant(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    grant_id: str
    identity_id: str
    capability: AuthorityCapability
    project_id: str
    target_prefix: str
    environment: str
    operation_class: str
    issued_by: str
    issued_at_utc: datetime = Field(default_factory=utc_now)
    expires_at_utc: datetime
    revoked_at_utc: datetime | None = None

    @field_validator("issued_at_utc", "expires_at_utc", "revoked_at_utc")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        return _aware(value) if value is not None else None

    @model_validator(mode="after")
    def validate_grant(self) -> CapabilityGrant:
        if not SECURITY_ID.fullmatch(self.grant_id) or not self.grant_id.startswith("GRANT-"):
            raise ValueError("invalid grant id")
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("grant must expire after issuance")
        if self.revoked_at_utc is not None and self.revoked_at_utc < self.issued_at_utc:
            raise ValueError("grant revocation cannot precede issuance")
        return self

    def active_at(self, when: datetime) -> bool:
        when = _aware(when)
        return self.revoked_at_utc is None and self.issued_at_utc <= when < self.expires_at_utc


class ApprovalRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    approval_id: str
    action_id: str
    proposer_identity_id: str
    approver_identity_id: str
    capability: AuthorityCapability
    decision: ApprovalDecision
    reason: str = Field(min_length=3, max_length=2000)
    correlation_id: str
    decided_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("decided_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_approval(self) -> ApprovalRecord:
        if not SECURITY_ID.fullmatch(self.approval_id) or not self.approval_id.startswith(
            "APPROVAL-"
        ):
            raise ValueError("invalid approval id")
        if self.proposer_identity_id == self.approver_identity_id:
            raise ValueError("approval identity must be independent from proposer")
        return self


class PolicyDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str
    policy_version: str
    action_id: str
    actor_identity_id: str
    capability: AuthorityCapability
    disposition: PolicyDisposition
    reasons: tuple[str, ...]
    constraints: dict[str, Any] = Field(default_factory=dict)
    approval_required: bool = False
    evaluated_at_utc: datetime = Field(default_factory=utc_now)
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("evaluated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_decision(self) -> PolicyDecision:
        if not SECURITY_ID.fullmatch(self.decision_id) or not self.decision_id.startswith(
            "POLICY-"
        ):
            raise ValueError("invalid policy decision id")
        if not self.reasons:
            raise ValueError("policy decision requires reasons")
        if self.disposition is PolicyDisposition.REQUIRE_APPROVAL and not self.approval_required:
            raise ValueError("require-approval disposition must mark approval_required")
        return self


class EgressRequest(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    request_id: str
    actor_identity_id: str
    project_id: str
    destination: str
    provider_id: str
    classification: DataClassification
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    context_keys: tuple[str, ...] = ()
    contains_secret: bool = False
    contains_untrusted_instructions: bool = False

    @model_validator(mode="after")
    def validate_request(self) -> EgressRequest:
        if not SECURITY_ID.fullmatch(self.request_id) or not self.request_id.startswith("EGRESS-"):
            raise ValueError("invalid egress request id")
        return self


class EgressDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str
    request_id: str
    disposition: PolicyDisposition
    allowed_context_keys: tuple[str, ...] = ()
    redacted_context_keys: tuple[str, ...] = ()
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_decision(self) -> EgressDecision:
        if not SECURITY_ID.fullmatch(self.decision_id) or not self.decision_id.startswith(
            "POLICY-"
        ):
            raise ValueError("invalid egress decision id")
        if not self.reasons:
            raise ValueError("egress decision requires reasons")
        return self


class SecretCapabilityReference(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    secret_ref_id: str
    logical_name: str = Field(min_length=1, max_length=200)
    backend: SecretBackendKind
    reference: str = Field(min_length=3, max_length=1000)
    classification: DataClassification = DataClassification.SECRET
    allowed_operations: tuple[str, ...]
    allowed_target_prefixes: tuple[str, ...]
    rotation_hint: str | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> SecretCapabilityReference:
        if not SECURITY_ID.fullmatch(self.secret_ref_id) or not self.secret_ref_id.startswith(
            "SREF-"
        ):
            raise ValueError("invalid secret reference id")
        if self.classification not in {DataClassification.SECRET, DataClassification.LOCAL_ONLY}:
            raise ValueError("secret capability must be SECRET or LOCAL_ONLY")
        if not self.allowed_operations or not self.allowed_target_prefixes:
            raise ValueError("secret capability requires operation and target scope")
        return self


class SecretLease(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    lease_id: str
    secret_ref_id: str
    identity_id: str
    project_id: str
    target: str
    operation: str
    issued_by: str
    issued_at_utc: datetime = Field(default_factory=utc_now)
    expires_at_utc: datetime
    revoked_at_utc: datetime | None = None
    materialization_count: int = Field(default=0, ge=0)

    @field_validator("issued_at_utc", "expires_at_utc", "revoked_at_utc")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        return _aware(value) if value is not None else None

    @model_validator(mode="after")
    def validate_lease(self) -> SecretLease:
        if not SECURITY_ID.fullmatch(self.lease_id) or not self.lease_id.startswith("SLEASE-"):
            raise ValueError("invalid secret lease id")
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("secret lease must expire after issuance")
        return self

    def active_at(self, when: datetime) -> bool:
        when = _aware(when)
        return self.revoked_at_utc is None and self.issued_at_utc <= when < self.expires_at_utc


class SecurityAuditEvent(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    audit_id: str
    event_type: str
    actor_identity_id: str
    target: str
    correlation_id: str
    outcome: str
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("occurred_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_event(self) -> SecurityAuditEvent:
        if not SECURITY_ID.fullmatch(self.audit_id) or not self.audit_id.startswith("SAUDIT-"):
            raise ValueError("invalid security audit id")
        return self


class SBOMComponent(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    component_id: str
    name: str
    version: str
    component_type: str
    license: str | None = None
    source: str | None = None
    metadata_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_component(self) -> SBOMComponent:
        if not SECURITY_ID.fullmatch(self.component_id) or not self.component_id.startswith(
            "SCOMP-"
        ):
            raise ValueError("invalid SBOM component id")
        return self


class SoftwareBillOfMaterials(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    sbom_id: str
    project_id: str
    source_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    components: tuple[SBOMComponent, ...]
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("generated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_sbom(self) -> SoftwareBillOfMaterials:
        if not SECURITY_ID.fullmatch(self.sbom_id) or not self.sbom_id.startswith("SBOM-"):
            raise ValueError("invalid SBOM id")
        if len({item.component_id for item in self.components}) != len(self.components):
            raise ValueError("SBOM components must be unique")
        return self


class SupplyChainFinding(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    finding_id: str
    kind: SupplyChainFindingKind
    severity: SupplyChainSeverity
    subject: str
    message: str
    source_tool: str
    evidence_path: str | None = None
    blocking: bool = False


class ScannerEvidence(DomainModel):
    """Normalized, content-bound evidence from one external scanner execution."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    scanner_evidence_id: str
    tool: str = Field(min_length=1, max_length=100)
    execution_state: Literal["SUCCEEDED", "FAILED"]
    source_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at_utc: datetime
    scanned_kinds: tuple[SupplyChainFindingKind, ...]
    findings: tuple[SupplyChainFinding, ...] = ()
    evidence_path: str | None = None

    @field_validator("observed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_evidence(self) -> ScannerEvidence:
        if not SECURITY_ID.fullmatch(
            self.scanner_evidence_id
        ) or not self.scanner_evidence_id.startswith("SCANEVID-"):
            raise ValueError("invalid scanner evidence id")
        if self.execution_state == "SUCCEEDED" and not self.scanned_kinds:
            raise ValueError("successful scanner evidence must identify scanned finding kinds")
        if len(set(self.scanned_kinds)) != len(self.scanned_kinds):
            raise ValueError("scanner evidence finding kinds must be unique")
        return self


class ArtifactIntegrityRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    integrity_id: str
    artifact_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    signature_state: Literal["NOT_REQUIRED", "UNVERIFIED", "VERIFIED", "FAILED"] = "UNVERIFIED"
    provenance_id: str | None = None

    @model_validator(mode="after")
    def validate_integrity(self) -> ArtifactIntegrityRecord:
        if not SECURITY_ID.fullmatch(self.integrity_id) or not self.integrity_id.startswith(
            "INTEGRITY-"
        ):
            raise ValueError("invalid integrity id")
        return self


class ReleaseProvenance(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    provenance_id: str
    project_id: str
    source_aggregate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    builder_identity_id: str
    sbom_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    verification_state: str
    evidence_ids: tuple[str, ...]
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("generated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_provenance(self) -> ReleaseProvenance:
        if not SECURITY_ID.fullmatch(self.provenance_id) or not self.provenance_id.startswith(
            "PROV-"
        ):
            raise ValueError("invalid provenance id")
        return self


class SupplyChainGateResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    gate_id: str
    state: GateState
    findings: tuple[SupplyChainFinding, ...]
    sbom_id: str | None = None
    integrity_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_gate(self) -> SupplyChainGateResult:
        if not SECURITY_ID.fullmatch(self.gate_id) or not self.gate_id.startswith("SGATE-"):
            raise ValueError("invalid supply-chain gate id")
        expected_fail = any(item.blocking for item in self.findings)
        if expected_fail and self.state is GateState.PASS:
            raise ValueError("supply-chain gate cannot pass with blocking findings")
        return self


class SelfModificationAssessment(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    assessment_id: str
    changed_paths: tuple[str, ...]
    touches_control_plane: bool
    required_review_classes: tuple[str, ...]
    requires_independent_review: bool
    requires_rollback_material: bool
    requires_security_verification: bool
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_assessment(self) -> SelfModificationAssessment:
        if not SECURITY_ID.fullmatch(self.assessment_id) or not self.assessment_id.startswith(
            "SELFCHG-"
        ):
            raise ValueError("invalid self-modification assessment id")
        if self.touches_control_plane and not self.requires_independent_review:
            raise ValueError("control-plane self-modification requires independent review")
        return self


class RootOfTrust(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    root_id: str
    bootstrap_identity_id: str
    trusted_policy_paths: tuple[str, ...]
    trusted_key_references: tuple[str, ...]
    recovery_procedure: str
    rotation_procedure: str
    revocation_procedure: str

    @model_validator(mode="after")
    def validate_root(self) -> RootOfTrust:
        if not SECURITY_ID.fullmatch(self.root_id) or not self.root_id.startswith("ROOTTRUST-"):
            raise ValueError("invalid root-of-trust id")
        if not self.trusted_policy_paths or not self.trusted_key_references:
            raise ValueError("root of trust requires trusted policy and key references")
        return self
