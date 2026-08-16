from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    EXTERNAL_MUTATION_DENIED = "EXTERNAL_MUTATION_DENIED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"
    NOT_FOUND = "NOT_FOUND"
    POLICY_DENIED = "POLICY_DENIED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass(slots=True)
class ProjectPipelineError(Exception):
    code: ErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }
