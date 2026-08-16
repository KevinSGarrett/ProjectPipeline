from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Strict immutable base for authoritative domain records."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def utc_now() -> datetime:
    return datetime.now(UTC)
