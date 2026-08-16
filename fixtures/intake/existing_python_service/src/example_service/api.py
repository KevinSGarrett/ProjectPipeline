from __future__ import annotations

from pydantic import BaseModel


class Health(BaseModel):
    status: str


def health() -> Health:
    return Health(status="ok")
