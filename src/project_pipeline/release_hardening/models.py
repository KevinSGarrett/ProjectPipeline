from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from project_pipeline.contracts.envelopes import ContractModel


class QualificationState(StrEnum):
    VERIFIED_LOCAL = "VERIFIED_LOCAL"
    CONFIGURED_PINNED_PROFILE = "CONFIGURED_PINNED_PROFILE"
    SOURCE_IMPLEMENTED_RUNTIME_NOT_QUALIFIED = "SOURCE_IMPLEMENTED_RUNTIME_NOT_QUALIFIED"
    ADAPTER_IMPLEMENTED_TOOL_UNAVAILABLE = "ADAPTER_IMPLEMENTED_TOOL_UNAVAILABLE"
    AVAILABLE_NOT_EXECUTED = "AVAILABLE_NOT_EXECUTED"
    BLOCKED_LICENSE_POLICY = "BLOCKED_LICENSE_POLICY"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"


class ToolQualification(ContractModel):
    upstream_id: str
    tool: str
    license: str
    allowed_role: str
    executable: str | None = None
    runtime_available: bool = False
    state: QualificationState
    authority: Literal["EVIDENCE_OR_MECHANICS_ONLY"] = "EVIDENCE_OR_MECHANICS_ONLY"
    notes: tuple[str, ...] = ()


class PackagingTargetQualification(ContractModel):
    target: str
    source_assets_present: bool
    runtime_available: bool
    state: QualificationState
    verification_command: str
    blockers: tuple[str, ...] = ()


class HardeningReport(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: Literal["PROJECT-PIPELINE"] = "PROJECT-PIPELINE"
    tool_qualifications: tuple[ToolQualification, ...]
    packaging_targets: tuple[PackagingTargetQualification, ...]
    environment_profiles: tuple[str, ...]
    supply_chain_state: str
    resolver_lock_state: str
    production_ready: Literal[False] = False
    production_blockers: tuple[str, ...]


class ReleaseCandidateSnapshot(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: Literal["PROJECT-PIPELINE"] = "PROJECT-PIPELINE"
    project_version: str
    candidate_label: str
    input_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    dependency_environment_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    resolver_lock_state: str
    migration_ids: tuple[str, ...]
    configuration_paths: tuple[str, ...]
    packaging_target_states: dict[str, str]
    completion_gate_state: str
    readiness: Literal["LOCAL_HARDENING_CANDIDATE_NOT_PRODUCTION_READY"] = (
        "LOCAL_HARDENING_CANDIDATE_NOT_PRODUCTION_READY"
    )
    blockers: tuple[str, ...]
    external_live_qualification_claimed: Literal[False] = False
