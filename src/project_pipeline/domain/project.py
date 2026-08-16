from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from project_pipeline.domain.base import DomainModel, utc_now
from project_pipeline.domain.identifiers import IdentifierKind, validate_identifier


class ProjectOrigin(StrEnum):
    NEW = "NEW"
    ADOPTED = "ADOPTED"


class RepositoryRole(StrEnum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    REFERENCE = "REFERENCE"


class ProjectRepository(DomainModel):
    repository_id: str = Field(min_length=3, max_length=191, pattern=r"^[a-z0-9][a-z0-9-]*$")
    root_path: str = Field(min_length=1, max_length=1024)
    role: RepositoryRole = RepositoryRole.PRIMARY
    canonical_url: str | None = Field(default=None, max_length=2048)


class ProjectManifest(DomainModel):
    """Domain manifest describing one controlled project, not the file-integrity manifest."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str
    project_name: str = Field(min_length=1, max_length=512)
    root_path: str = Field(min_length=1, max_length=1024)
    origin: ProjectOrigin = ProjectOrigin.ADOPTED
    profile: str = Field(min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)
    repositories: tuple[ProjectRepository, ...]
    source_registry_path: str
    requirement_registry_path: str
    plan_catalog_path: str
    jira_index_path: str
    evidence_ledger_path: str
    created_at_utc: datetime = Field(default_factory=utc_now)
    updated_at_utc: datetime = Field(default_factory=utc_now)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return validate_identifier(value, IdentifierKind.PROJECT)

    @field_validator("created_at_utc", "updated_at_utc")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("project manifest timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("repositories")
    @classmethod
    def require_primary_repository(
        cls, values: tuple[ProjectRepository, ...]
    ) -> tuple[ProjectRepository, ...]:
        if not values:
            raise ValueError("project manifest requires at least one repository")
        if sum(item.role is RepositoryRole.PRIMARY for item in values) != 1:
            raise ValueError("project manifest requires exactly one primary repository")
        identifiers = [item.repository_id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("project repository identifiers must be unique")
        return values

    def semantic_fingerprint(self) -> str:
        document = self.model_dump(mode="json", exclude={"created_at_utc", "updated_at_utc"})
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def primary_repository(self) -> ProjectRepository:
        return next(item for item in self.repositories if item.role is RepositoryRole.PRIMARY)

    def resolved_root(self, repository_root: Path) -> Path:
        path = Path(self.root_path)
        return path.resolve() if path.is_absolute() else (repository_root / path).resolve()
