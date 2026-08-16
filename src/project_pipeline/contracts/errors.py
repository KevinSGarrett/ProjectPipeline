from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from project_pipeline.contracts.envelopes import ContractModel, Identifier


class AdapterErrorCategory(StrEnum):
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    CONFLICT = "CONFLICT"
    DEPENDENCY = "DEPENDENCY"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    TRANSIENT = "TRANSIENT"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    UNAVAILABLE = "UNAVAILABLE"
    PERMANENT = "PERMANENT"


class AdapterErrorPayload(ContractModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    error_code: str = Field(min_length=3, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")
    category: AdapterErrorCategory
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool
    unknown_outcome: bool = False
    provider: Identifier
    operation: Identifier
    correlation_id: Identifier
    external_operation_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_semantics(self) -> AdapterErrorPayload:
        retryable = {
            AdapterErrorCategory.RATE_LIMIT,
            AdapterErrorCategory.TIMEOUT,
            AdapterErrorCategory.TRANSIENT,
            AdapterErrorCategory.UNKNOWN_OUTCOME,
            AdapterErrorCategory.UNAVAILABLE,
        }
        permanent = {
            AdapterErrorCategory.AUTHENTICATION,
            AdapterErrorCategory.AUTHORIZATION,
            AdapterErrorCategory.INVALID_REQUEST,
            AdapterErrorCategory.NOT_FOUND,
            AdapterErrorCategory.PERMANENT,
        }
        if self.category in retryable and not self.retryable:
            raise ValueError(f"{self.category} must be retryable")
        if self.category in permanent and self.retryable:
            raise ValueError(f"{self.category} cannot be retryable")
        if self.category is AdapterErrorCategory.UNKNOWN_OUTCOME and not self.unknown_outcome:
            raise ValueError("UNKNOWN_OUTCOME category must set unknown_outcome")
        return self
