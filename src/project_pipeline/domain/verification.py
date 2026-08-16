from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now

VERIFICATION_ID = re.compile(
    r"^(VTOOL|VCHK|VRUN|VART|GJOURNEY|GRESULT|BROWSE|A11Y|PERF|PROP|MUTATE|FAULT|PMERGE|VPORT|VIMPACT)-[A-F0-9]{20}$"
)


def verification_identifier(
    prefix: Literal[
        "VTOOL",
        "VCHK",
        "VRUN",
        "VART",
        "GJOURNEY",
        "GRESULT",
        "BROWSE",
        "A11Y",
        "PERF",
        "PROP",
        "MUTATE",
        "FAULT",
        "PMERGE",
        "VPORT",
        "VIMPACT",
    ],
    *parts: str,
) -> str:
    if not parts or any(not str(part).strip() for part in parts):
        raise ValueError("verification identifier parts must be non-empty")
    payload = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def verification_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class VerificationCategory(StrEnum):
    CONTRACT = "CONTRACT"
    API = "API"
    INTEGRATION = "INTEGRATION"
    END_TO_END = "END_TO_END"
    GOLDEN_JOURNEY = "GOLDEN_JOURNEY"
    BROWSER = "BROWSER"
    VISUAL = "VISUAL"
    ACCESSIBILITY = "ACCESSIBILITY"
    PERFORMANCE = "PERFORMANCE"
    ADVERSARIAL = "ADVERSARIAL"
    PROPERTY = "PROPERTY"
    MUTATION = "MUTATION"
    FAULT = "FAULT"
    POST_MERGE = "POST_MERGE"


class VerificationResultState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class ToolActivationState(StrEnum):
    EXECUTED = "EXECUTED"
    ADAPTER_IMPLEMENTED = "ADAPTER_IMPLEMENTED"
    QUALIFIED_NOT_INSTALLED = "QUALIFIED_NOT_INSTALLED"
    PATTERN_ONLY = "PATTERN_ONLY"
    DEFERRED_TO_LATER_SURFACE = "DEFERRED_TO_LATER_SURFACE"


class ArtifactKind(StrEnum):
    LOG = "LOG"
    JSON = "JSON"
    SCREENSHOT = "SCREENSHOT"
    TRACE = "TRACE"
    HTML = "HTML"
    REPORT = "REPORT"


class VerificationToolActivation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    activation_id: str
    upstream_id: str
    repository: str
    state: ToolActivationState
    installed_version: str | None = None
    executable_path: str | None = None
    integration_paths: tuple[str, ...] = ()
    evidence_paths: tuple[str, ...] = ()
    activation_phase: str
    reason: str
    source_revision: str | None = None
    license: str | None = None

    @model_validator(mode="after")
    def validate_activation(self) -> VerificationToolActivation:
        if not VERIFICATION_ID.fullmatch(self.activation_id) or not self.activation_id.startswith(
            "VTOOL-"
        ):
            raise ValueError("invalid verification tool activation id")
        if self.state is ToolActivationState.EXECUTED and not self.evidence_paths:
            raise ValueError("executed tool activation requires evidence")
        if (
            self.state
            in {
                ToolActivationState.EXECUTED,
                ToolActivationState.ADAPTER_IMPLEMENTED,
            }
            and not self.integration_paths
        ):
            raise ValueError("implemented/executed tool activation requires integration paths")
        return self


class VerificationCheckSpec(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    check_id: str
    name: str = Field(min_length=3, max_length=200)
    category: VerificationCategory
    required: bool = True
    command: tuple[str, ...] = ()
    timeout_seconds: int = Field(default=120, ge=1, le=7200)
    upstream_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    evidence_max_age_seconds: int = Field(default=86400, ge=1)
    description: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def validate_check(self) -> VerificationCheckSpec:
        if not VERIFICATION_ID.fullmatch(self.check_id) or not self.check_id.startswith("VCHK-"):
            raise ValueError("invalid verification check id")
        expected = verification_identifier(
            "VCHK", self.name, self.category.value, str(self.required), self.description
        )
        if self.check_id != expected:
            raise ValueError("verification check id does not match check semantics")
        return self


class VerificationArtifact(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: str
    kind: ArtifactKind
    relative_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str
    produced_by_check_id: str

    @model_validator(mode="after")
    def validate_artifact(self) -> VerificationArtifact:
        if not VERIFICATION_ID.fullmatch(self.artifact_id) or not self.artifact_id.startswith(
            "VART-"
        ):
            raise ValueError("invalid verification artifact id")
        if self.relative_path.startswith(("/", "\\")) or ".." in self.relative_path.replace(
            "\\", "/"
        ).split("/"):
            raise ValueError("verification artifact path must be repository-relative and contained")
        return self


class VerificationCheckResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    check_id: str
    state: VerificationResultState
    required: bool
    category: VerificationCategory
    duration_ms: int = Field(ge=0)
    reason: str
    stdout_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    stderr_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    artifacts: tuple[VerificationArtifact, ...] = ()
    started_at_utc: datetime = Field(default_factory=utc_now)
    completed_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_result(self) -> VerificationCheckResult:
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("completion cannot precede start")
        if self.required and self.state is VerificationResultState.SKIPPED:
            raise ValueError("required verification checks may not be silently skipped")
        return self


class VerificationRun(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str
    project_id: str
    profile: str
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    results: tuple[VerificationCheckResult, ...]
    final_state: VerificationResultState
    required_fail_count: int = Field(ge=0)
    required_blocked_count: int = Field(ge=0)
    optional_skipped_count: int = Field(ge=0)
    started_at_utc: datetime = Field(default_factory=utc_now)
    completed_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_run(self) -> VerificationRun:
        if not VERIFICATION_ID.fullmatch(self.run_id) or not self.run_id.startswith("VRUN-"):
            raise ValueError("invalid verification run id")
        failures = sum(
            item.required and item.state is VerificationResultState.FAIL for item in self.results
        )
        blocked = sum(
            item.required and item.state is VerificationResultState.BLOCKED for item in self.results
        )
        skipped = sum(
            (not item.required) and item.state is VerificationResultState.SKIPPED
            for item in self.results
        )
        if (failures, blocked, skipped) != (
            self.required_fail_count,
            self.required_blocked_count,
            self.optional_skipped_count,
        ):
            raise ValueError("verification run counts do not match results")
        expected_state = (
            VerificationResultState.FAIL
            if failures
            else VerificationResultState.BLOCKED
            if blocked
            else VerificationResultState.PASS
        )
        if self.final_state is not expected_state:
            raise ValueError("verification run final state does not match required results")
        return self


class GoldenJourneyDefinition(DomainModel):
    schema_version: Literal["1.1.0"] = "1.1.0"
    journey_id: str
    name: str = Field(min_length=3, max_length=200)
    objective: str = Field(min_length=8, max_length=2000)
    requirement_ids: tuple[str, ...]
    environment: str = Field(min_length=3, max_length=500)
    setup_steps: tuple[str, ...]
    action_steps: tuple[str, ...]
    expected_results: tuple[str, ...]
    cleanup_steps: tuple[str, ...]
    evidence_expectations: tuple[str, ...]
    required_observations: tuple[str, ...]
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "HIGH"

    @model_validator(mode="after")
    def validate_journey(self) -> GoldenJourneyDefinition:
        if not VERIFICATION_ID.fullmatch(self.journey_id) or not self.journey_id.startswith(
            "GJOURNEY-"
        ):
            raise ValueError("invalid golden journey id")
        expected = verification_identifier("GJOURNEY", self.name, self.objective)
        if self.journey_id != expected:
            raise ValueError("golden journey id does not match semantics")
        if not self.requirement_ids:
            raise ValueError("golden journey requires requirement traceability")
        for field_name in (
            "setup_steps",
            "action_steps",
            "expected_results",
            "cleanup_steps",
            "evidence_expectations",
            "required_observations",
        ):
            values = getattr(self, field_name)
            if not values or any(not value.strip() for value in values):
                raise ValueError(f"golden journey requires non-empty {field_name}")
        return self


class VerificationImpactSet(DomainModel):
    schema_version: Literal["1.1.0"] = "1.1.0"
    impact_id: str
    changed_paths: tuple[str, ...]
    dependency_paths: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    acceptance_methods: tuple[str, ...] = ()
    profile_categories: tuple[VerificationCategory, ...] = ()
    required_categories: tuple[VerificationCategory, ...]
    rationale: tuple[str, ...]

    @model_validator(mode="after")
    def validate_impact(self) -> VerificationImpactSet:
        if not VERIFICATION_ID.fullmatch(self.impact_id) or not self.impact_id.startswith(
            "VIMPACT-"
        ):
            raise ValueError("invalid verification impact id")
        if not self.changed_paths and not self.dependency_paths and not self.requirement_ids:
            raise ValueError(
                "test impact requires changed paths, dependency paths, or requirement links"
            )
        if not self.required_categories:
            raise ValueError("test impact must select at least one verification category")
        if not self.rationale:
            raise ValueError("test impact requires rationale")
        changed = tuple(sorted(dict.fromkeys(self.changed_paths)))
        dependencies = tuple(sorted(dict.fromkeys(self.dependency_paths)))
        requirements = tuple(sorted(dict.fromkeys(self.requirement_ids)))
        methods = tuple(
            sorted(
                dict.fromkeys(
                    item.strip().lower() for item in self.acceptance_methods if item.strip()
                )
            )
        )
        profile = tuple(sorted(dict.fromkeys(self.profile_categories), key=lambda item: item.value))
        categories = tuple(
            sorted(dict.fromkeys(self.required_categories), key=lambda item: item.value)
        )
        expected = verification_identifier(
            "VIMPACT",
            *changed,
            *dependencies,
            *requirements,
            self.risk,
            *methods,
            *(item.value for item in profile),
            *(item.value for item in categories),
        )
        if self.impact_id != expected:
            raise ValueError("verification impact id does not match semantics")
        return self


class GoldenJourneyResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    result_id: str
    journey_id: str
    state: VerificationResultState
    observations: tuple[str, ...]
    evidence_paths: tuple[str, ...] = ()
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_result(self) -> GoldenJourneyResult:
        if not VERIFICATION_ID.fullmatch(self.result_id) or not self.result_id.startswith(
            "GRESULT-"
        ):
            raise ValueError("invalid golden journey result id")
        return self


class BrowserEvidence(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    browser_evidence_id: str
    target: str
    browser_name: str
    browser_version: str
    viewport_width: int = Field(gt=0)
    viewport_height: int = Field(gt=0)
    screenshot_path: str
    screenshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    horizontal_overflow: bool
    console_error_count: int = Field(ge=0)
    load_duration_ms: int = Field(ge=0)
    passed: bool

    @model_validator(mode="after")
    def validate_browser(self) -> BrowserEvidence:
        if not VERIFICATION_ID.fullmatch(
            self.browser_evidence_id
        ) or not self.browser_evidence_id.startswith("BROWSE-"):
            raise ValueError("invalid browser evidence id")
        if self.passed and (self.horizontal_overflow or self.console_error_count):
            raise ValueError("passing browser evidence cannot contain overflow or console errors")
        return self


class AccessibilityEvidence(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    accessibility_id: str
    target: str
    method: str
    rule_count: int = Field(ge=0)
    violation_count: int = Field(ge=0)
    violations: tuple[str, ...] = ()
    passed: bool

    @model_validator(mode="after")
    def validate_accessibility(self) -> AccessibilityEvidence:
        if not VERIFICATION_ID.fullmatch(
            self.accessibility_id
        ) or not self.accessibility_id.startswith("A11Y-"):
            raise ValueError("invalid accessibility id")
        if self.passed != (self.violation_count == 0):
            raise ValueError("accessibility pass state must match violation count")
        return self


class PerformanceResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    performance_id: str
    subject: str
    sample_count: int = Field(ge=1)
    p50_ms: int = Field(ge=0)
    p95_ms: int = Field(ge=0)
    max_ms: int = Field(ge=0)
    budget_p95_ms: int = Field(gt=0)
    passed: bool

    @model_validator(mode="after")
    def validate_performance(self) -> PerformanceResult:
        if not VERIFICATION_ID.fullmatch(self.performance_id) or not self.performance_id.startswith(
            "PERF-"
        ):
            raise ValueError("invalid performance id")
        if not (self.p50_ms <= self.p95_ms <= self.max_ms):
            raise ValueError("performance percentiles must be monotonic")
        if self.passed != (self.p95_ms <= self.budget_p95_ms):
            raise ValueError("performance pass state must match budget")
        return self


class PropertyProbeResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    property_id: str
    property_name: str
    case_count: int = Field(ge=1)
    seed: int
    failure_count: int = Field(ge=0)
    passed: bool
    failure_examples: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_property(self) -> PropertyProbeResult:
        if not VERIFICATION_ID.fullmatch(self.property_id) or not self.property_id.startswith(
            "PROP-"
        ):
            raise ValueError("invalid property probe id")
        if self.passed != (self.failure_count == 0):
            raise ValueError("property pass state must match failure count")
        return self


class MutationProbeResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    mutation_id: str
    mutation_name: str
    detector: str
    detected: bool
    evidence_path: str | None = None

    @model_validator(mode="after")
    def validate_mutation(self) -> MutationProbeResult:
        if not VERIFICATION_ID.fullmatch(self.mutation_id) or not self.mutation_id.startswith(
            "MUTATE-"
        ):
            raise ValueError("invalid mutation probe id")
        return self


class FaultScenarioResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    fault_id: str
    scenario: str
    injected_fault: str
    expected_behavior: str
    observed_behavior: str
    passed: bool

    @model_validator(mode="after")
    def validate_fault(self) -> FaultScenarioResult:
        if not VERIFICATION_ID.fullmatch(self.fault_id) or not self.fault_id.startswith("FAULT-"):
            raise ValueError("invalid fault scenario id")
        return self


class PostMergeReport(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    report_id: str
    repository_manifest_ok: bool
    repository_validation_ok: bool
    traceability_ok: bool
    evidence_integrity_ok: bool
    required_test_suite_ok: bool
    final_passed: bool
    observations: tuple[str, ...]

    @model_validator(mode="after")
    def validate_report(self) -> PostMergeReport:
        if not VERIFICATION_ID.fullmatch(self.report_id) or not self.report_id.startswith(
            "PMERGE-"
        ):
            raise ValueError("invalid post-merge report id")
        expected = all(
            (
                self.repository_manifest_ok,
                self.repository_validation_ok,
                self.traceability_ok,
                self.evidence_integrity_ok,
                self.required_test_suite_ok,
            )
        )
        if self.final_passed != expected:
            raise ValueError("post-merge final state must match component checks")
        return self


class VerificationPortfolioSnapshot(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    portfolio_id: str
    project_id: str
    activations: tuple[VerificationToolActivation, ...]
    required_categories: tuple[VerificationCategory, ...]
    category_coverage: dict[str, int]
    activation_review_complete: bool
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_portfolio(self) -> VerificationPortfolioSnapshot:
        if not VERIFICATION_ID.fullmatch(self.portfolio_id) or not self.portfolio_id.startswith(
            "VPORT-"
        ):
            raise ValueError("invalid verification portfolio id")
        return self
