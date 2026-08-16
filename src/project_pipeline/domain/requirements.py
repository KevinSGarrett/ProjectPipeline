from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel
from project_pipeline.domain.identifiers import IdentifierKind, validate_identifier
from project_pipeline.source_references import parse_source_reference


class ImplementationState(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    PARTIALLY_IMPLEMENTED = "PARTIALLY_IMPLEMENTED"
    MOCK_VERIFIED = "MOCK_VERIFIED"
    LIVE_VERIFIED = "LIVE_VERIFIED"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    PLANNED_ONLY = "PLANNED_ONLY"


class RequirementDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"
    EXCLUDED = "EXCLUDED"
    BLOCKED = "BLOCKED"


class RequirementRecord(DomainModel):
    """Typed representation of one authoritative requirement registry row."""

    schema_version: Literal["2.0.0"] = "2.0.0"
    requirement_id: str
    domain: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z]+$")
    title: str = Field(min_length=1, max_length=1000)
    statement: str = Field(min_length=1, max_length=4000)
    requirement_type: str = Field(min_length=1, max_length=64)
    normative_strength: str = Field(min_length=1, max_length=32)
    authority_classification: str = Field(min_length=1, max_length=64)
    source_references: tuple[str, ...]
    source_sequence: int = Field(ge=0)
    source_kind: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=4000)
    priority: str = Field(pattern=r"^P[0-3]$")
    risk: str = Field(min_length=1, max_length=32)
    disposition: RequirementDisposition
    disposition_reason: str = Field(min_length=1, max_length=4000)
    implementation_state: ImplementationState
    plan_ids: tuple[str, ...]
    plan_section_ids: tuple[str, ...]
    decision_ids: tuple[str, ...] = ()
    open_decision_ids: tuple[str, ...] = ()
    evolution_ids: tuple[str, ...] = ()
    jira_ids: tuple[str, ...]
    implementation_paths: tuple[str, ...] = ()
    test_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    verification_class: str = Field(min_length=1, max_length=64)
    verification_expectation: str = Field(min_length=1, max_length=4000)
    acceptance_summary: str = Field(min_length=1, max_length=4000)
    tags: tuple[str, ...] = ()
    superseded_by_requirement_ids: tuple[str, ...] = ()
    supersedes_requirement_ids: tuple[str, ...] = ()

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.REQUIREMENT)

    @field_validator("source_references")
    @classmethod
    def validate_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("requirement must retain at least one exact source reference")
        for value in values:
            parse_source_reference(value)
        return values

    @field_validator("plan_ids")
    @classmethod
    def validate_plans(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("requirement must map to at least one plan")
        for value in values:
            validate_identifier(value, IdentifierKind.PLAN)
        return values

    @field_validator("plan_section_ids")
    @classmethod
    def validate_plan_sections(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("requirement must map to at least one plan section")
        for value in values:
            validate_identifier(value, IdentifierKind.PLAN_SECTION)
        return values

    @field_validator("jira_ids")
    @classmethod
    def validate_jira_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("requirement must map to at least one work item")
        for value in values:
            validate_identifier(value, IdentifierKind.ISSUE)
        return values

    @field_validator("decision_ids")
    @classmethod
    def validate_decisions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            validate_identifier(value, IdentifierKind.DECISION)
        return values

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            validate_identifier(value, IdentifierKind.EVIDENCE)
        return values

    @field_validator(
        "source_references",
        "plan_ids",
        "plan_section_ids",
        "decision_ids",
        "open_decision_ids",
        "evolution_ids",
        "jira_ids",
        "implementation_paths",
        "test_ids",
        "evidence_ids",
        "tags",
        "superseded_by_requirement_ids",
        "supersedes_requirement_ids",
    )
    @classmethod
    def reject_duplicates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("requirement relation lists cannot contain duplicates")
        return values

    @model_validator(mode="after")
    def require_completion_evidence(self) -> RequirementRecord:
        complete_states = {
            ImplementationState.IMPLEMENTED,
            ImplementationState.MOCK_VERIFIED,
            ImplementationState.LIVE_VERIFIED,
        }
        if self.implementation_state in complete_states and (
            not self.implementation_paths or not self.test_ids or not self.evidence_ids
        ):
            raise ValueError(
                "implemented requirement records require implementation, test, and evidence links"
            )
        return self

    def as_registry_row(self) -> dict[str, object]:
        return self.model_dump(mode="json")
