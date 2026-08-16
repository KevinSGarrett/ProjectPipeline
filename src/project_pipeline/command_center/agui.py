from __future__ import annotations

from typing import Any
from uuid import uuid4

from project_pipeline.command_center.models import CommandCenterSnapshot
from project_pipeline.contracts import EventEnvelope


class AGUIAdapter:
    """AG-UI compatible transport documents; Project Pipeline EventEnvelope remains authoritative."""

    protocol_name = "AG-UI"
    compatibility_profile = "project-pipeline-pass19"

    @staticmethod
    def run_started(*, thread_id: str, run_id: str) -> dict[str, Any]:
        return {"type": "RUN_STARTED", "threadId": thread_id, "runId": run_id}

    @staticmethod
    def run_finished(*, thread_id: str, run_id: str) -> dict[str, Any]:
        return {"type": "RUN_FINISHED", "threadId": thread_id, "runId": run_id}

    @staticmethod
    def run_error(*, message: str) -> dict[str, Any]:
        return {"type": "RUN_ERROR", "message": message}

    @staticmethod
    def state_snapshot(snapshot: CommandCenterSnapshot) -> dict[str, Any]:
        return {"type": "STATE_SNAPSHOT", "snapshot": snapshot.model_dump(mode="json")}

    @staticmethod
    def custom_event(event: EventEnvelope) -> dict[str, Any]:
        return {"type": "CUSTOM", "name": event.event_type, "value": event.model_dump(mode="json")}

    @staticmethod
    def text_events(
        text: str, *, message_id: str | None = None, role: str = "assistant"
    ) -> tuple[dict[str, Any], ...]:
        mid = message_id or f"message-{uuid4()}"
        return (
            {"type": "TEXT_MESSAGE_START", "messageId": mid, "role": role},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": text},
            {"type": "TEXT_MESSAGE_END", "messageId": mid},
        )

    @staticmethod
    def validate_run(events: tuple[dict[str, Any], ...]) -> None:
        if not events or events[0].get("type") != "RUN_STARTED":
            raise ValueError("AG-UI run must start with RUN_STARTED")
        if events[-1].get("type") not in {"RUN_FINISHED", "RUN_ERROR"}:
            raise ValueError("AG-UI run must terminate with RUN_FINISHED or RUN_ERROR")
        forbidden = {"CHAIN_OF_THOUGHT", "PRIVATE_REASONING", "HIDDEN_REASONING"}
        if any(str(e.get("type", "")).upper() in forbidden for e in events):
            raise ValueError("private reasoning is never exposed through the operator transport")
