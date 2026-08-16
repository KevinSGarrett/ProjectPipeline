from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from project_pipeline.core.errors import ProjectPipelineError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Result(Generic[T]):
    value: T | None = None
    error: ProjectPipelineError | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.error is None):
            raise ValueError("Result requires exactly one of value or error")

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def success(cls, value: T) -> Result[T]:
        return cls(value=value)

    @classmethod
    def failure(cls, error: ProjectPipelineError) -> Result[T]:
        return cls(error=error)

    def unwrap(self) -> T:
        if self.error is not None:
            raise self.error
        if self.value is None:
            raise RuntimeError("Result invariant was violated")
        return self.value
