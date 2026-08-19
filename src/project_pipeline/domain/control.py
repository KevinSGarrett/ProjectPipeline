from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.domain.identifiers import IdentifierKind, validate_identifier
from project_pipeline.domain.state import TaskLifecycleState

CONTROL_ID = re.compile(r"^(CTRL|SEQ|SCOPE|COMPLETE)-[A-F0-9]{20}$")


def control_identifier(prefix: Literal["CTRL", "SEQ", "SCOPE", "COMPLETE"], *parts: str) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("control identifier parts must be non-empty")
    canonical = "\x1f".join(str(part).strip() for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20].upper()
    return f"{prefix}-{digest}"


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EligibilityState(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    ALREADY_ACTIVE = "ALREADY_ACTIVE"
    TERMINAL = "TERMINAL"
    BLOCKED = "BLOCKED"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    PRODUCT_SCOPE_PAUSED = "PRODUCT_SCOPE_PAUSED"
    POLICY_DENIED = "POLICY_DENIED"


class ReadinessState(StrEnum):
    READY = "READY"
    WAITING_DEPENDENCIES = "WAITING_DEPENDENCIES"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CONTEXT = "WAITING_CONTEXT"
    WAITING_RESOURCES = "WAITING_RESOURCES"
    WAITING_ENVIRONMENT = "WAITING_ENVIRONMENT"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ACTIVE = "ACTIVE"
    TERMINAL = "TERMINAL"


class ScopeFindingKind(StrEnum):
    REQUIREMENT_WITHOUT_WORK = "REQUIREMENT_WITHOUT_WORK"
    WORK_WITHOUT_REQUIREMENT = "WORK_WITHOUT_REQUIREMENT"
    UNKNOWN_REQUIREMENT = "UNKNOWN_REQUIREMENT"
    UNKNOWN_DEPENDENCY = "UNKNOWN_DEPENDENCY"
    DONE_WITHOUT_EVIDENCE = "DONE_WITHOUT_EVIDENCE"
    DONE_WITHOUT_IMPLEMENTATION = "DONE_WITHOUT_IMPLEMENTATION"
    IMPLEMENTED_REQUIREMENT_WITHOUT_ARTIFACT = "IMPLEMENTED_REQUIREMENT_WITHOUT_ARTIFACT"


class CompletionProjectionState(StrEnum):
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    READY_FOR_COMPLETION_GATE = "READY_FOR_COMPLETION_GATE"


class ControlCohortCounts(DomainModel):
    """Labeled same-snapshot denominators for facts, eligibility, and readiness."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    total_work_items: int = Field(ge=0, default=0)
    reconciliation_facts: int = Field(ge=0, default=0)
    structural_container_facts: int = Field(ge=0, default=0)
    leaf_reconciliation_facts: int = Field(ge=0, default=0)
    eligibility_reconciliation: int = Field(ge=0, default=0)
    eligibility_eligible: int = Field(ge=0, default=0)
    eligibility_policy_denied: int = Field(ge=0, default=0)
    eligibility_product_scope_paused: int = Field(ge=0, default=0)
    eligibility_terminal: int = Field(ge=0, default=0)
    eligibility_already_active: int = Field(ge=0, default=0)
    eligibility_blocked: int = Field(ge=0, default=0)
    eligibility_blocked_external: int = Field(ge=0, default=0)
    dependency_ready: int = Field(ge=0, default=0)


class TaskControlFact(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    project_id: str
    state: TaskLifecycleState
    issue_type: Literal["EPIC", "STORY", "TASK", "SUBTASK", "BUG", "SPIKE"] = "TASK"
    priority: str = Field(pattern=r"^P[0-3]$")
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    dependency_ids: tuple[str, ...] = ()
    blocker_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    accepted: bool = True
    policy_eligible: bool = True
    approval_required: bool = False
    approval_satisfied: bool = True
    context_required: bool = False
    context_satisfied: bool = True
    resources_available: bool = True
    environment_available: bool = True
    external_blocked: bool = False
    reconciliation_required: bool = False
    remote_readback_required: bool = False
    product_scope_allowed: bool = True
    expected_duration_minutes: int | None = Field(default=None, ge=1, le=525_600)
    deadline_utc: datetime | None = None

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @field_validator("dependency_ids", "blocker_ids")
    @classmethod
    def validate_task_relations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("control task relations cannot contain duplicates")
        for value in values:
            validate_identifier(value, IdentifierKind.ISSUE)
        return values

    @field_validator("requirement_ids")
    @classmethod
    def validate_requirement_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("requirement relations cannot contain duplicates")
        for value in values:
            validate_identifier(value, IdentifierKind.REQUIREMENT)
        return values

    @field_validator("deadline_utc")
    @classmethod
    def normalize_deadline(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("task deadline must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_semantics(self) -> TaskControlFact:
        if self.task_id in self.dependency_ids or self.task_id in self.blocker_ids:
            raise ValueError("control task cannot depend on or be blocked by itself")
        if self.approval_required and self.approval_satisfied is False:
            return self
        return self

    def semantic_fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class TaskEligibility(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    state: EligibilityState
    eligible: bool
    reasons: tuple[str, ...] = ()

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @model_validator(mode="after")
    def validate_result(self) -> TaskEligibility:
        if self.eligible != (self.state is EligibilityState.ELIGIBLE):
            raise ValueError("eligibility boolean must agree with eligibility state")
        if not self.eligible and not self.reasons:
            raise ValueError("ineligible tasks require at least one reason")
        return self


class TaskReadiness(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    state: ReadinessState
    ready: bool
    unresolved_dependencies: tuple[str, ...] = ()
    unresolved_blockers: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @model_validator(mode="after")
    def validate_result(self) -> TaskReadiness:
        if self.ready != (self.state is ReadinessState.READY):
            raise ValueError("readiness boolean must agree with readiness state")
        if not self.ready and not self.reasons:
            raise ValueError("non-ready tasks require at least one reason")
        return self


class CriticalPathAnalysis(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    path: tuple[str, ...]
    total_duration_minutes: int = Field(ge=0)
    duration_source: Literal["DECLARED", "MIXED", "DEFAULT_HEURISTIC", "EMPTY"]
    earliest_finish_minutes: dict[str, int]
    slack_minutes: dict[str, int]

    @field_validator("path")
    @classmethod
    def validate_path(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            validate_identifier(value, IdentifierKind.ISSUE)
        return values


class SequenceScore(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    priority_score: int
    critical_path_score: int
    deadline_score: int
    risk_score: int
    unblock_score: int
    duration_score: int
    total_score: int

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)

    @model_validator(mode="after")
    def validate_total(self) -> SequenceScore:
        expected = (
            self.priority_score
            + self.critical_path_score
            + self.deadline_score
            + self.risk_score
            + self.unblock_score
            + self.duration_score
        )
        if self.total_score != expected:
            raise ValueError("sequence score total does not match its components")
        return self


class SequenceItem(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    rank: int = Field(ge=1)
    task_id: str
    readiness: ReadinessState
    score: SequenceScore
    dependency_depth: int = Field(ge=0)
    downstream_count: int = Field(ge=0)
    on_critical_path: bool

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.ISSUE)


class BuildSequence(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    sequence_id: str
    project_id: str
    graph_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    task_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    critical_path: CriticalPathAnalysis
    ordered_ready_work: tuple[SequenceItem, ...]
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("sequence_id")
    @classmethod
    def validate_sequence_id(cls, value: str) -> str:
        if not CONTROL_ID.fullmatch(value) or not value.startswith("SEQ-"):
            raise ValueError(f"invalid sequence identifier: {value}")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @field_validator("generated_at_utc")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("sequence timestamp must be timezone-aware")
        return value.astimezone(UTC)


class ScopeFinding(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    kind: ScopeFindingKind
    subject_id: str
    related_id: str | None = None
    detail: str = Field(min_length=1, max_length=2000)


class ScopeReconciliationReport(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    report_id: str
    project_id: str
    requirement_count: int = Field(ge=0)
    work_item_count: int = Field(ge=0)
    findings: tuple[ScopeFinding, ...]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        if not CONTROL_ID.fullmatch(value) or not value.startswith("SCOPE-"):
            raise ValueError(f"invalid scope report identifier: {value}")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)


class CompletionProjection(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    projection_id: str
    project_id: str
    state: CompletionProjectionState
    total_work_items: int = Field(ge=0)
    completed_work_items: int = Field(ge=0)
    active_work_items: int = Field(ge=0)
    blocked_work_items: int = Field(ge=0)
    failed_work_items: int = Field(ge=0)
    accepted_requirements: int = Field(ge=0)
    implemented_or_external_blocked_requirements: int = Field(ge=0)
    ready_work_items: int = Field(ge=0)
    verification_eligible: bool
    final_completion_gate_satisfied: bool = False
    reasons: tuple[str, ...]
    cohorts: ControlCohortCounts = Field(default_factory=ControlCohortCounts)
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("projection_id")
    @classmethod
    def validate_projection_id(cls, value: str) -> str:
        if not CONTROL_ID.fullmatch(value) or not value.startswith("COMPLETE-"):
            raise ValueError(f"invalid completion projection identifier: {value}")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @model_validator(mode="after")
    def preserve_completion_authority(self) -> CompletionProjection:
        if self.final_completion_gate_satisfied:
            raise ValueError(
                "control-plane completion projection cannot satisfy the independent Completion Gate"
            )
        if self.verification_eligible != (
            self.state is CompletionProjectionState.READY_FOR_COMPLETION_GATE
        ):
            raise ValueError("verification eligibility must agree with completion projection state")
        return self


class ControlSnapshot(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: str
    project_id: str
    sequence: BuildSequence
    scope: ScopeReconciliationReport
    completion: CompletionProjection
    eligibility: tuple[TaskEligibility, ...]
    readiness: tuple[TaskReadiness, ...]
    snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        if not CONTROL_ID.fullmatch(value) or not value.startswith("CTRL-"):
            raise ValueError(f"invalid control snapshot identifier: {value}")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)
