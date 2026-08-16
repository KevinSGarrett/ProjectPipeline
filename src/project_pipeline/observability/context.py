from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    project_id: str | None = None
    workflow_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    actor_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None

    def as_attributes(self) -> dict[str, str]:
        return {key: value for key, value in asdict(self).items() if value is not None}


_EMPTY_CONTEXT = CorrelationContext()
_CURRENT_CONTEXT: ContextVar[CorrelationContext] = ContextVar(
    "project_pipeline_correlation_context", default=_EMPTY_CONTEXT
)


def current_context() -> CorrelationContext:
    return _CURRENT_CONTEXT.get()


def set_context(context: CorrelationContext) -> Token[CorrelationContext]:
    return _CURRENT_CONTEXT.set(context)


def reset_context(token: Token[CorrelationContext]) -> None:
    _CURRENT_CONTEXT.reset(token)


@contextmanager
def correlation_scope(**values: str | None) -> Iterator[CorrelationContext]:
    unknown = sorted(set(values) - set(CorrelationContext.__dataclass_fields__))
    if unknown:
        raise ValueError(f"unknown correlation context fields: {unknown}")
    current = current_context()
    document = asdict(current)
    document.update(values)
    merged = CorrelationContext(**document)
    token = set_context(merged)
    try:
        yield merged
    finally:
        reset_context(token)
