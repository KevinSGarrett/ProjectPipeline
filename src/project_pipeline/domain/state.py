from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.domain.identifiers import (
    IdentifierKind,
    deterministic_identifier,
    validate_identifier,
)


class ProjectLifecycleState(StrEnum):
    REGISTERED = "REGISTERED"
    COMPILING = "COMPILING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class TaskLifecycleState(StrEnum):
    BACKLOG = "BACKLOG"
    READY = "READY"
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    IN_REVIEW = "IN_REVIEW"
    VALIDATING = "VALIDATING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


PROJECT_TRANSITIONS: dict[ProjectLifecycleState, frozenset[ProjectLifecycleState]] = {
    ProjectLifecycleState.REGISTERED: frozenset(
        {ProjectLifecycleState.COMPILING, ProjectLifecycleState.BLOCKED}
    ),
    ProjectLifecycleState.COMPILING: frozenset(
        {ProjectLifecycleState.READY, ProjectLifecycleState.BLOCKED, ProjectLifecycleState.FAILED}
    ),
    ProjectLifecycleState.READY: frozenset(
        {
            ProjectLifecycleState.ACTIVE,
            ProjectLifecycleState.BLOCKED,
            ProjectLifecycleState.ARCHIVED,
        }
    ),
    ProjectLifecycleState.ACTIVE: frozenset(
        {
            ProjectLifecycleState.BLOCKED,
            ProjectLifecycleState.VERIFYING,
            ProjectLifecycleState.FAILED,
        }
    ),
    ProjectLifecycleState.BLOCKED: frozenset(
        {
            ProjectLifecycleState.COMPILING,
            ProjectLifecycleState.READY,
            ProjectLifecycleState.ACTIVE,
            ProjectLifecycleState.FAILED,
        }
    ),
    ProjectLifecycleState.VERIFYING: frozenset(
        {
            ProjectLifecycleState.ACTIVE,
            ProjectLifecycleState.BLOCKED,
            ProjectLifecycleState.COMPLETED,
            ProjectLifecycleState.FAILED,
        }
    ),
    ProjectLifecycleState.COMPLETED: frozenset(
        {ProjectLifecycleState.ACTIVE, ProjectLifecycleState.ARCHIVED}
    ),
    ProjectLifecycleState.FAILED: frozenset(
        {
            ProjectLifecycleState.COMPILING,
            ProjectLifecycleState.BLOCKED,
            ProjectLifecycleState.ARCHIVED,
        }
    ),
    ProjectLifecycleState.ARCHIVED: frozenset(),
}

TASK_TRANSITIONS: dict[TaskLifecycleState, frozenset[TaskLifecycleState]] = {
    TaskLifecycleState.BACKLOG: frozenset(
        {TaskLifecycleState.READY, TaskLifecycleState.BLOCKED, TaskLifecycleState.CANCELLED}
    ),
    TaskLifecycleState.READY: frozenset(
        {TaskLifecycleState.CLAIMED, TaskLifecycleState.BLOCKED, TaskLifecycleState.CANCELLED}
    ),
    TaskLifecycleState.CLAIMED: frozenset(
        {
            TaskLifecycleState.READY,
            TaskLifecycleState.IN_PROGRESS,
            TaskLifecycleState.BLOCKED,
        }
    ),
    TaskLifecycleState.IN_PROGRESS: frozenset(
        {
            TaskLifecycleState.BLOCKED,
            TaskLifecycleState.IN_REVIEW,
            TaskLifecycleState.FAILED,
        }
    ),
    TaskLifecycleState.BLOCKED: frozenset(
        {
            TaskLifecycleState.BACKLOG,
            TaskLifecycleState.READY,
            TaskLifecycleState.IN_PROGRESS,
            TaskLifecycleState.CANCELLED,
        }
    ),
    TaskLifecycleState.IN_REVIEW: frozenset(
        {
            TaskLifecycleState.IN_PROGRESS,
            TaskLifecycleState.VALIDATING,
            TaskLifecycleState.BLOCKED,
        }
    ),
    TaskLifecycleState.VALIDATING: frozenset(
        {
            TaskLifecycleState.IN_PROGRESS,
            TaskLifecycleState.BLOCKED,
            TaskLifecycleState.DONE,
            TaskLifecycleState.FAILED,
        }
    ),
    TaskLifecycleState.DONE: frozenset({TaskLifecycleState.IN_PROGRESS}),
    TaskLifecycleState.FAILED: frozenset(
        {TaskLifecycleState.READY, TaskLifecycleState.IN_PROGRESS, TaskLifecycleState.CANCELLED}
    ),
    TaskLifecycleState.CANCELLED: frozenset({TaskLifecycleState.BACKLOG}),
}


class ProjectStateRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str
    state: ProjectLifecycleState
    version: int = Field(default=1, ge=1)
    manifest_revision: int = Field(default=1, ge=1)
    blocked_reason: str | None = Field(default=None, max_length=2000)
    task_counts: dict[str, int] = Field(default_factory=dict)
    last_transition_id: str | None = None
    updated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @field_validator("updated_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("state timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_block_reason(self) -> ProjectStateRecord:
        if self.state is ProjectLifecycleState.BLOCKED and not self.blocked_reason:
            raise ValueError("blocked project state requires a reason")
        if self.state is not ProjectLifecycleState.BLOCKED and self.blocked_reason:
            raise ValueError("blocked reason is only valid for BLOCKED project state")
        if any(value < 0 for value in self.task_counts.values()):
            raise ValueError("task counts cannot be negative")
        return self


class TaskStateRecord(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    project_id: str
    state: TaskLifecycleState
    version: int = Field(default=1, ge=1)
    priority: str = Field(default="P1", pattern=r"^P[0-3]$")
    dependency_ids: tuple[str, ...] = ()
    blocker_ids: tuple[str, ...] = ()
    owner_id: str | None = Field(default=None, max_length=191)
    blocked_reason: str | None = Field(default=None, max_length=2000)
    last_transition_id: str | None = None
    updated_at_utc: datetime = Field(default_factory=utc_now)

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
    def validate_related_tasks(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("task relation lists cannot contain duplicates")
        for value in values:
            validate_identifier(value, IdentifierKind.ISSUE)
        return values

    @field_validator("updated_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("state timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_state_metadata(self) -> TaskStateRecord:
        if self.task_id in self.dependency_ids or self.task_id in self.blocker_ids:
            raise ValueError("task cannot depend on or be blocked by itself")
        if self.state is TaskLifecycleState.BLOCKED and not self.blocked_reason:
            raise ValueError("blocked task state requires a reason")
        if self.state is not TaskLifecycleState.BLOCKED and self.blocked_reason:
            raise ValueError("blocked reason is only valid for BLOCKED task state")
        return self


class DomainStateTransition(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    transition_id: str
    entity_type: Literal["project", "task"]
    entity_id: str
    previous_state: str
    next_state: str
    expected_version: int = Field(ge=1)
    resulting_version: int = Field(ge=2)
    reason: str = Field(min_length=1, max_length=2000)
    actor_id: str = Field(min_length=3, max_length=191)
    correlation_id: str = Field(min_length=3, max_length=191)
    occurred_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("transition_id")
    @classmethod
    def validate_transition_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.TRANSITION)

    @field_validator("occurred_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transition timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_versions_and_state(self) -> DomainStateTransition:
        if self.previous_state == self.next_state:
            raise ValueError("state transition cannot be a no-op")
        if self.resulting_version != self.expected_version + 1:
            raise ValueError("resulting version must increment expected version by one")
        return self

    @classmethod
    def create(
        cls,
        *,
        entity_type: Literal["project", "task"],
        entity_id: str,
        previous_state: str,
        next_state: str,
        expected_version: int,
        reason: str,
        actor_id: str,
        correlation_id: str,
    ) -> DomainStateTransition:
        identifier = deterministic_identifier(
            IdentifierKind.TRANSITION,
            entity_type,
            entity_id,
            previous_state,
            next_state,
            str(expected_version),
            reason,
            actor_id,
            correlation_id,
        )
        return cls(
            transition_id=identifier.value,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_state=previous_state,
            next_state=next_state,
            expected_version=expected_version,
            resulting_version=expected_version + 1,
            reason=reason,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )


def ensure_project_transition(
    previous: ProjectLifecycleState, next_state: ProjectLifecycleState
) -> None:
    if next_state not in PROJECT_TRANSITIONS[previous]:
        raise ValueError(f"invalid project transition: {previous.value} -> {next_state.value}")


def ensure_task_transition(previous: TaskLifecycleState, next_state: TaskLifecycleState) -> None:
    if next_state not in TASK_TRANSITIONS[previous]:
        raise ValueError(f"invalid task transition: {previous.value} -> {next_state.value}")


def task_state_from_jira(value: str) -> TaskLifecycleState:
    mapping = {
        "BACKLOG": TaskLifecycleState.BACKLOG,
        "READY": TaskLifecycleState.READY,
        "IN_PROGRESS": TaskLifecycleState.IN_PROGRESS,
        "IN_REVIEW": TaskLifecycleState.IN_REVIEW,
        "VALIDATION": TaskLifecycleState.VALIDATING,
        "VALIDATING": TaskLifecycleState.VALIDATING,
        "BLOCKED": TaskLifecycleState.BLOCKED,
        "DONE": TaskLifecycleState.DONE,
        "FAILED": TaskLifecycleState.FAILED,
        "CANCELLED": TaskLifecycleState.CANCELLED,
    }
    try:
        return mapping[value]
    except KeyError as error:
        raise ValueError(f"unsupported Jira lifecycle state: {value}") from error
