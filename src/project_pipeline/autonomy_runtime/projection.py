"""Project compatibility storage enums to live external-precondition language.

Persisted ``HUMAN_REQUIRED`` remains a compatibility storage value. Live reports,
Command Center snapshots, and scheduler-facing status must project
``BLOCKED_EXTERNAL`` and must not assign work to a person.
"""

from __future__ import annotations

from typing import Any

COMPATIBILITY_HUMAN_REQUIRED = "HUMAN_REQUIRED"
LIVE_EXTERNAL_PRECONDITION = "BLOCKED_EXTERNAL"
_FORBIDDEN_LIVE_PHRASES = (
    "operator session",
    "await human",
    "awaiting human",
    "next human",
    "human-owned",
    "HUMAN_REQUIRED",
)


def project_runtime_state(value: str) -> str:
    if value == COMPATIBILITY_HUMAN_REQUIRED:
        return LIVE_EXTERNAL_PRECONDITION
    return value


def is_compatibility_human_required(value: str) -> bool:
    return value == COMPATIBILITY_HUMAN_REQUIRED


def project_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    projected = dict(payload)
    state = projected.get("state")
    if isinstance(state, str):
        projected["state"] = project_runtime_state(state)
        if is_compatibility_human_required(state):
            projected["stored_state"] = COMPATIBILITY_HUMAN_REQUIRED
            projected["unavailable_capability"] = projected.get("reason") or projected.get(
                "unavailable_capability", "external_precondition"
            )
    return projected


def live_text_is_forbidden(value: str) -> bool:
    return any(phrase in value for phrase in _FORBIDDEN_LIVE_PHRASES)
