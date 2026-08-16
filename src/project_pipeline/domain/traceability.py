from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.domain.identifiers import (
    IdentifierKind,
    deterministic_identifier,
    validate_identifier,
)
from project_pipeline.source_references import parse_source_reference


class TraceabilityLinkType(StrEnum):
    SOURCE = "SOURCE"
    PLAN = "PLAN"
    PLAN_SECTION = "PLAN_SECTION"
    JIRA = "JIRA"
    IMPLEMENTATION = "IMPLEMENTATION"
    TEST = "TEST"
    EVIDENCE = "EVIDENCE"
    DECISION = "DECISION"
    OPEN_DECISION = "OPEN_DECISION"
    EVOLUTION = "EVOLUTION"


class TraceabilityAuthority(StrEnum):
    AUTHORITATIVE_CATALOG = "AUTHORITATIVE_CATALOG"
    PERSISTED_PROJECTION = "PERSISTED_PROJECTION"
    PROPOSED_CHANGE = "PROPOSED_CHANGE"


class TraceabilityLink(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    link_id: str
    requirement_id: str
    link_type: TraceabilityLinkType
    target: str = Field(min_length=1, max_length=2048)
    ordinal: int = Field(default=0, ge=0)
    authority: TraceabilityAuthority = TraceabilityAuthority.AUTHORITATIVE_CATALOG
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("link_id")
    @classmethod
    def validate_link_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.TRACE_LINK)

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.REQUIREMENT)

    @model_validator(mode="after")
    def validate_target(self) -> TraceabilityLink:
        if self.link_type is TraceabilityLinkType.SOURCE:
            parse_source_reference(self.target)
        elif self.link_type is TraceabilityLinkType.PLAN:
            validate_identifier(self.target, IdentifierKind.PLAN)
        elif self.link_type is TraceabilityLinkType.PLAN_SECTION:
            validate_identifier(self.target, IdentifierKind.PLAN_SECTION)
        elif self.link_type is TraceabilityLinkType.JIRA:
            validate_identifier(self.target, IdentifierKind.ISSUE)
        elif self.link_type is TraceabilityLinkType.EVIDENCE:
            validate_identifier(self.target, IdentifierKind.EVIDENCE)
        elif self.link_type is TraceabilityLinkType.DECISION:
            validate_identifier(self.target, IdentifierKind.DECISION)
        elif self.link_type in {
            TraceabilityLinkType.IMPLEMENTATION,
            TraceabilityLinkType.TEST,
        } and (self.target.startswith("/") or "\x00" in self.target):
            raise ValueError("repository paths and test identifiers must be relative and safe")
        return self

    @classmethod
    def create(
        cls,
        *,
        requirement_id: str,
        link_type: TraceabilityLinkType,
        target: str,
        ordinal: int = 0,
        authority: TraceabilityAuthority = TraceabilityAuthority.AUTHORITATIVE_CATALOG,
        metadata: dict[str, Any] | None = None,
    ) -> TraceabilityLink:
        identifier = deterministic_identifier(
            IdentifierKind.TRACE_LINK,
            requirement_id,
            link_type.value,
            target,
            authority.value,
        )
        return cls(
            link_id=identifier.value,
            requirement_id=requirement_id,
            link_type=link_type,
            target=target,
            ordinal=ordinal,
            authority=authority,
            metadata=metadata or {},
        )


class TraceabilityMutation(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    requirement_id: str
    operation: Literal["ADD", "REMOVE"]
    link_type: TraceabilityLinkType
    target: str
    expected_revision: int = Field(ge=1)
    actor_id: str = Field(min_length=3, max_length=191)
    correlation_id: str = Field(min_length=3, max_length=191)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.REQUIREMENT)


class TraceabilityMutationResult(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    mutation_id: str
    requirement_id: str
    operation: Literal["ADD", "REMOVE"]
    link: TraceabilityLink
    previous_revision: int = Field(ge=1)
    resulting_revision: int = Field(ge=1)
    changed: bool
    authority_state: TraceabilityAuthority = TraceabilityAuthority.PROPOSED_CHANGE
    recorded_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("mutation_id")
    @classmethod
    def validate_mutation_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.MUTATION)

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.REQUIREMENT)

    @model_validator(mode="after")
    def validate_revision_change(self) -> TraceabilityMutationResult:
        expected = self.previous_revision + (1 if self.changed else 0)
        if self.resulting_revision != expected:
            raise ValueError(
                "resulting_revision must increment exactly once only when the mutation changes state"
            )
        if self.recorded_at_utc.tzinfo is None:
            raise ValueError("recorded_at_utc must be timezone-aware")
        return self
