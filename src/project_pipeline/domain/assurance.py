from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now

ASSURANCE_ID = re.compile(
    r"^(CRIT|VPLAN|TRUTH|REVIEW|GATE|LOOP|SCOPE|SCHANGE|CAND|FAIL|SIM)-[A-F0-9]{20}$"
)


def assurance_identifier(
    prefix: Literal[
        "CRIT",
        "VPLAN",
        "TRUTH",
        "REVIEW",
        "GATE",
        "LOOP",
        "SCOPE",
        "SCHANGE",
        "CAND",
        "FAIL",
        "SIM",
    ],
    *parts: str,
) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("assurance identifier parts must be non-empty")
    payload = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def assurance_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class VerificationMethod(StrEnum):
    STATIC = "STATIC"
    UNIT = "UNIT"
    COMPONENT = "COMPONENT"
    CONTRACT = "CONTRACT"
    API = "API"
    INTEGRATION = "INTEGRATION"
    END_TO_END = "END_TO_END"
    PROPERTY = "PROPERTY"
    MUTATION = "MUTATION"
    ADVERSARIAL = "ADVERSARIAL"
    FAULT = "FAULT"
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    ACCESSIBILITY = "ACCESSIBILITY"
    VISUAL = "VISUAL"
    BROWSER = "BROWSER"
    RESILIENCE = "RESILIENCE"
    RECOVERY = "RECOVERY"
    INSTALLER = "INSTALLER"
    UPGRADE = "UPGRADE"
    ROLLBACK = "ROLLBACK"
    REVIEW = "REVIEW"
    TRACEABILITY = "TRACEABILITY"
    DOCUMENTATION = "DOCUMENTATION"


class AssuranceRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CriterionState(StrEnum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


class TruthKind(StrEnum):
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"
    VERIFIED_FACT = "VERIFIED_FACT"
    UNKNOWN = "UNKNOWN"
    CONTRADICTED = "CONTRADICTED"


class GateState(StrEnum):
    COMPLETE = "COMPLETE"
    NOT_COMPLETE = "NOT_COMPLETE"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"


class LoopDisposition(StrEnum):
    CONTINUE = "CONTINUE"
    REQUIRE_NOVELTY = "REQUIRE_NOVELTY"
    STOP_AND_ESCALATE = "STOP_AND_ESCALATE"


class CandidateCompletionState(StrEnum):
    CHALLENGE = "CHALLENGE"
    READY_FOR_COMPLETION_GATE = "READY_FOR_COMPLETION_GATE"
    NOT_READY = "NOT_READY"


class ScopeChangeDisposition(StrEnum):
    WITHIN_FROZEN_SCOPE = "WITHIN_FROZEN_SCOPE"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    CHANGE_BUDGET_EXHAUSTED = "CHANGE_BUDGET_EXHAUSTED"


class FailureCategory(StrEnum):
    REQUIREMENT = "REQUIREMENT"
    TRACEABILITY = "TRACEABILITY"
    WORK = "WORK"
    TEST = "TEST"
    GOLDEN_JOURNEY = "GOLDEN_JOURNEY"
    SECURITY = "SECURITY"
    RESILIENCE = "RESILIENCE"
    DEPLOYMENT = "DEPLOYMENT"
    ROLLBACK = "ROLLBACK"
    DOCUMENTATION = "DOCUMENTATION"
    CONTINUATION = "CONTINUATION"
    STATE_RECONCILIATION = "STATE_RECONCILIATION"
    COVERAGE = "COVERAGE"
    EVIDENCE = "EVIDENCE"
    REVIEW = "REVIEW"
    SCOPE = "SCOPE"


class AcceptanceCriterion(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    criterion_id: str
    work_item_id: str
    statement: str = Field(min_length=8, max_length=4000)
    requirement_ids: tuple[str, ...] = ()
    risk: AssuranceRisk = AssuranceRisk.MEDIUM
    verification_methods: tuple[VerificationMethod, ...]
    verification_command: str | None = None
    verification_path: str | None = None
    fixture_paths: tuple[str, ...] = ()
    objective: bool = True
    frozen_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> AcceptanceCriterion:
        if not ASSURANCE_ID.fullmatch(self.criterion_id) or not self.criterion_id.startswith(
            "CRIT-"
        ):
            raise ValueError("invalid criterion id")
        if not self.verification_methods:
            raise ValueError("criterion requires at least one verification method")
        expected = assurance_identifier(
            "CRIT", self.work_item_id, self.statement, self.frozen_fingerprint
        )
        if self.criterion_id != expected:
            raise ValueError("criterion id does not match criterion semantics")
        return self


class VerificationPlan(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    plan_id: str
    project_id: str
    criteria: tuple[AcceptanceCriterion, ...]
    required_method_counts: dict[str, int] = Field(default_factory=dict)
    independent_review_required: bool = False
    max_verification_attempts: int = Field(default=8, ge=1, le=100)
    max_evidence_records: int = Field(default=40, ge=1, le=1000)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("generated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_plan(self) -> VerificationPlan:
        if not ASSURANCE_ID.fullmatch(self.plan_id) or not self.plan_id.startswith("VPLAN-"):
            raise ValueError("invalid verification plan id")
        if len({item.criterion_id for item in self.criteria}) != len(self.criteria):
            raise ValueError("verification plan criteria must be unique")
        return self


class TruthRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    truth_id: str
    subject_id: str
    kind: TruthKind
    statement: str = Field(min_length=1, max_length=4000)
    evidence_ids: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    producer_id: str | None = None
    verification_status: Literal["UNVERIFIED", "VERIFIED", "SUPERSEDED", "CONFLICTED"] = (
        "UNVERIFIED"
    )
    confidence_milli: int | None = Field(default=None, ge=0, le=1000)
    observed_at_utc: datetime = Field(default_factory=utc_now)
    fresh_until_utc: datetime | None = None
    supersedes_truth_id: str | None = None

    @field_validator("observed_at_utc", "fresh_until_utc")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)

    @model_validator(mode="after")
    def validate_truth(self) -> TruthRecord:
        if not ASSURANCE_ID.fullmatch(self.truth_id) or not self.truth_id.startswith("TRUTH-"):
            raise ValueError("invalid truth id")
        if self.kind is TruthKind.VERIFIED_FACT and not self.evidence_ids:
            raise ValueError("verified facts require evidence")
        if self.kind is TruthKind.VERIFIED_FACT and self.verification_status != "VERIFIED":
            raise ValueError("verified facts require VERIFIED status")
        if self.kind is TruthKind.UNKNOWN and self.evidence_ids:
            raise ValueError("unknown truth cannot carry passing evidence")
        if self.kind is TruthKind.UNKNOWN and self.verification_status == "VERIFIED":
            raise ValueError("unknown truth cannot be VERIFIED")
        if self.fresh_until_utc is not None and self.fresh_until_utc < self.observed_at_utc:
            raise ValueError("truth freshness deadline cannot precede observation")
        return self


class EvidenceAssessment(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    evidence_id: str
    criterion_id: str
    state: CriterionState
    method: VerificationMethod
    producer_id: str
    observed_at_utc: datetime
    age_seconds: int = Field(ge=0)
    max_age_seconds: int = Field(gt=0)
    reason: str

    @field_validator("observed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)


class ReviewerIdentity(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    reviewer_id: str = Field(min_length=1, max_length=191)
    implementer_id: str = Field(min_length=1, max_length=191)
    context_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    implementation_context_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    conflicts: tuple[str, ...] = ()

    @property
    def independent(self) -> bool:
        return (
            self.reviewer_id != self.implementer_id
            and self.context_fingerprint != self.implementation_context_fingerprint
            and not self.conflicts
        )


class IndependentReview(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    review_id: str
    subject_id: str
    identity: ReviewerIdentity
    criterion_ids: tuple[str, ...]
    finding_count: int = Field(ge=0)
    blocking_finding_count: int = Field(ge=0)
    evidence_ids: tuple[str, ...] = ()
    completed_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("completed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_review(self) -> IndependentReview:
        if not ASSURANCE_ID.fullmatch(self.review_id) or not self.review_id.startswith("REVIEW-"):
            raise ValueError("invalid review id")
        return self


class AttemptObservation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    attempt_number: int = Field(ge=1)
    action_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    tool_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    state_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    failure_signature: str | None = None
    novelty_dimensions: tuple[
        Literal["HYPOTHESIS", "INPUT", "TOOL", "ENVIRONMENT", "RECOVERY_STRATEGY"], ...
    ] = ()
    progress_units: int = Field(default=0, ge=0)


class AttemptBudget(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    max_attempts: int = Field(default=5, ge=1, le=100)
    used_attempts: int = Field(default=0, ge=0)
    max_same_failure: int = Field(default=2, ge=1, le=20)
    max_unchanged_outputs: int = Field(default=2, ge=1, le=20)

    @model_validator(mode="after")
    def validate_budget(self) -> AttemptBudget:
        if self.used_attempts > self.max_attempts:
            raise ValueError("used attempts cannot exceed max attempts")
        return self


class LoopGuardDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str
    task_id: str
    disposition: LoopDisposition
    attempts_used: int = Field(ge=0)
    repeated_failure_count: int = Field(ge=0)
    unchanged_output_count: int = Field(ge=0)
    repeated_action_count: int = Field(ge=0)
    progress_detected: bool
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_decision(self) -> LoopGuardDecision:
        if not ASSURANCE_ID.fullmatch(self.decision_id) or not self.decision_id.startswith("LOOP-"):
            raise ValueError("invalid loop decision id")
        return self


class ScopeContract(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    scope_id: str
    work_item_id: str
    included_behavior: tuple[str, ...]
    excluded_behavior: tuple[str, ...]
    allowed_paths: tuple[str, ...] = ()
    escalation_conditions: tuple[str, ...]
    frozen_criteria_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    change_budget: int = Field(default=3, ge=0, le=100)
    consumed_changes: int = Field(default=0, ge=0)
    frozen_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("frozen_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_scope(self) -> ScopeContract:
        if not ASSURANCE_ID.fullmatch(self.scope_id) or not self.scope_id.startswith("SCOPE-"):
            raise ValueError("invalid scope id")
        if self.consumed_changes > self.change_budget:
            raise ValueError("consumed changes cannot exceed change budget")
        if not self.included_behavior or not self.escalation_conditions:
            raise ValueError("scope requires included behavior and escalation conditions")
        return self


class ScopeChangeDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    change_id: str
    scope_id: str
    disposition: ScopeChangeDisposition
    requested_behavior: tuple[str, ...] = ()
    requested_paths: tuple[str, ...] = ()
    material: bool
    remaining_change_budget: int = Field(ge=0)
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_change(self) -> ScopeChangeDecision:
        if not ASSURANCE_ID.fullmatch(self.change_id) or not self.change_id.startswith("SCHANGE-"):
            raise ValueError("invalid scope change id")
        return self


class CandidateCompletionAssessment(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    assessment_id: str
    work_item_id: str
    state: CandidateCompletionState
    implementer_id: str
    criteria_total: int = Field(ge=0)
    criteria_passing: int = Field(ge=0)
    stale_evidence_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    independent_review_required: bool
    independent_review_satisfied: bool
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_candidate(self) -> CandidateCompletionAssessment:
        if not ASSURANCE_ID.fullmatch(self.assessment_id) or not self.assessment_id.startswith(
            "CAND-"
        ):
            raise ValueError("invalid candidate assessment id")
        if self.criteria_passing > self.criteria_total:
            raise ValueError("passing criteria cannot exceed total")
        return self


class CompletionQuestionResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    question_number: int = Field(ge=1, le=16)
    question: str
    passed: bool
    externally_blocked: bool = False
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()


class CompletionFailure(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    failure_id: str
    category: FailureCategory
    subject_id: str
    detail: str
    rework_route: str

    @model_validator(mode="after")
    def validate_failure(self) -> CompletionFailure:
        if not ASSURANCE_ID.fullmatch(self.failure_id) or not self.failure_id.startswith("FAIL-"):
            raise ValueError("invalid completion failure id")
        return self


class CompletionGateFacts(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str
    source_requirements_dispositioned: bool
    accepted_requirements_complete_or_external: bool
    implementation_traceability_complete: bool
    critical_paths_tested: bool
    golden_journeys_pass: bool
    security_gates_satisfied: bool
    resilience_verified: bool
    deployment_reproducible: bool
    rollback_verified: bool
    engineer_operable_from_docs: bool
    ai_continuable_from_repo_and_jira: bool
    unresolved_items_truthful: bool
    command_center_truthful: bool
    jira_truthful: bool
    unattended_operating_loop_qualified: bool
    unexplained_gap_count: int = Field(ge=0)
    externally_blocked_question_numbers: tuple[int, ...] = ()
    evidence_by_question: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    reasons_by_question: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class CompletionGateDecision(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    gate_id: str
    project_id: str
    state: GateState
    questions: tuple[CompletionQuestionResult, ...]
    failures: tuple[CompletionFailure, ...]
    source_snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    final_complete: bool
    evaluated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("evaluated_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_gate(self) -> CompletionGateDecision:
        if not ASSURANCE_ID.fullmatch(self.gate_id) or not self.gate_id.startswith("GATE-"):
            raise ValueError("invalid completion gate id")
        passed = all(item.passed for item in self.questions)
        if self.final_complete != passed:
            raise ValueError("final_complete must equal all completion questions passing")
        if self.state is GateState.COMPLETE and not self.final_complete:
            raise ValueError("COMPLETE gate state requires all questions to pass")
        if self.final_complete and self.failures:
            raise ValueError("complete gate cannot contain failures")
        return self


class AssuranceSimulationResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    simulation_id: str
    scenario: str
    passed: bool
    observations: tuple[str, ...]

    @model_validator(mode="after")
    def validate_sim(self) -> AssuranceSimulationResult:
        if not ASSURANCE_ID.fullmatch(self.simulation_id) or not self.simulation_id.startswith(
            "SIM-"
        ):
            raise ValueError("invalid assurance simulation id")
        return self
