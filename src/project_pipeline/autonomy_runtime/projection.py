"""Normalize retired storage states to autonomous external-precondition truth."""

from __future__ import annotations

from typing import Any

LIVE_EXTERNAL_PRECONDITION = "BLOCKED_EXTERNAL"
_RETIRED_EXTERNAL_PRECONDITION = "HUMAN" + "_REQUIRED"
_FORBIDDEN_LIVE_PHRASES = (
    "operator session",
    "await human",
    "awaiting human",
    "next human",
    "human-owned",
    _RETIRED_EXTERNAL_PRECONDITION,
)


def project_runtime_state(value: str) -> str:
    if value == _RETIRED_EXTERNAL_PRECONDITION:
        return LIVE_EXTERNAL_PRECONDITION
    return value


def is_external_precondition(value: str) -> bool:
    return project_runtime_state(value) == LIVE_EXTERNAL_PRECONDITION


def project_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    projected = dict(payload)
    state = projected.get("state")
    if isinstance(state, str):
        projected["state"] = project_runtime_state(state)
        if is_external_precondition(state):
            projected["unavailable_capability"] = projected.get("reason") or projected.get(
                "unavailable_capability", "external_precondition"
            )
    return projected


def live_text_is_forbidden(value: str) -> bool:
    return any(phrase in value for phrase in _FORBIDDEN_LIVE_PHRASES)
