from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator

from project_pipeline.contracts.envelopes import ContractModel


class DiagnosticStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class DiagnosticCheck(ContractModel):
    check_id: str = Field(min_length=3, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")
    status: DiagnosticStatus
    summary: str = Field(min_length=1, max_length=1000)
    details: dict[str, Any] = Field(default_factory=dict)


class DiagnosticSnapshot(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    observed_at_utc: datetime
    project_id: str
    profile: str
    overall_status: DiagnosticStatus
    checks: tuple[DiagnosticCheck, ...]

    @field_validator("observed_at_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at_utc must be timezone-aware")
        return value.astimezone(UTC)
