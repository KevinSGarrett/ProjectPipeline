from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol
from uuid import uuid4

from project_pipeline.command_center.models import (
    CommandCenterScope,
    CommandCenterSnapshot,
    DirectorActionProposal,
    DirectorChatMessage,
    DirectorChatRequest,
    DirectorChatResponse,
    DirectorContext,
    DirectorMessageRole,
    IncidentCase,
)
from project_pipeline.contracts import CommandEnvelope, CommandResult
from project_pipeline.core.command_bus import CommandProcessor


class DirectorContextBuilder:
    _forbidden_tokens = ("chain_of_thought", "private_reasoning", "hidden_reasoning", "scratchpad")

    def build(
        self,
        snapshot: CommandCenterSnapshot,
        *,
        scope: CommandCenterScope,
        incident_id: str | None = None,
        source_ids: tuple[str, ...] = (),
        incident: IncidentCase | None = None,
    ) -> DirectorContext:
        facts = self._scrub(snapshot.model_dump(mode="json"))
        if incident is not None:
            facts = {**facts, "incident": self._scrub(incident.model_dump(mode="json"))}
        return DirectorContext(
            scope=scope,
            project_id=snapshot.project_id,
            incident_id=incident_id,
            snapshot_fingerprint=snapshot.fingerprint,
            facts=facts,
            source_ids=source_ids,
        )

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._scrub(item)
                for key, item in value.items()
                if all(token not in key.lower() for token in self._forbidden_tokens)
            }
        if isinstance(value, list):
            return [self._scrub(item) for item in value]
        return value


class DirectorResponder(Protocol):
    def respond(
        self, context: DirectorContext, message: str
    ) -> tuple[str, tuple[DirectorActionProposal, ...], tuple[str, ...]]: ...


class DeterministicGroundedDirectorResponder:
    """Fail-closed responder used when no qualified model adapter is configured.

    It provides useful state summaries and typed action proposals without pretending that a
    model-generated answer or hidden reasoning exists.
    """

    def respond(
        self, context: DirectorContext, message: str
    ) -> tuple[str, tuple[DirectorActionProposal, ...], tuple[str, ...]]:
        facts = context.facts
        question = message.strip().lower()
        evidence_values: list[str] = []
        for health in facts.get("health", []) if isinstance(facts.get("health", []), list) else []:
            if isinstance(health, dict):
                evidence_values.extend(
                    str(value) for value in health.get("evidence_ids", []) if isinstance(value, str)
                )
        incident = facts.get("incident")
        if isinstance(incident, dict):
            evidence_values.extend(
                str(value) for value in incident.get("evidence_ids", []) if isinstance(value, str)
            )
        evidence = tuple(dict.fromkeys(evidence_values))
        proposals: list[DirectorActionProposal] = []
        if "pause new work" in question:
            proposals.append(
                self._proposal(context, "project.pause_new_work", "Pause admission of new work")
            )
        if "pause project" in question:
            proposals.append(self._proposal(context, "project.pause", "Pause project execution"))
        if "emergency stop" in question:
            proposals.append(
                self._proposal(
                    context,
                    "project.emergency_stop",
                    "Request emergency stop through normal control gates",
                )
            )

        if context.scope is CommandCenterScope.INCIDENT:
            incident = facts.get("incident", {})
            raw = incident.get("incident", {}) if isinstance(incident, dict) else {}
            summary = raw.get(
                "summary", "Incident details are unavailable from the authorized projection."
            )
            exact_action = raw.get(
                "exact_human_action", "Use the Recovery Center for the canonical requested action."
            )
            verification = raw.get("verification_steps", [])
            answer = (
                f"Incident {context.incident_id}: {summary} Exact operator action: {exact_action} "
                f"Verification steps: {', '.join(verification) if verification else 'see canonical incident record'}."
            )
        else:
            health = facts.get("overall_health", "UNKNOWN")
            gate = facts.get("completion_gate_state", "UNKNOWN")
            completion = facts.get("completion_percent")
            work = facts.get("live_work", [])
            incidents = facts.get("active_incident_ids", [])
            completion_text = "unknown" if completion is None else f"{float(completion):.1f}%"
            answer = (
                f"Authorized {context.scope.value.lower()} state: health={health}, "
                f"completion_gate={gate}, completion={completion_text}, "
                f"live_work={len(work) if isinstance(work, list) else 0}, "
                f"active_incidents={len(incidents) if isinstance(incidents, list) else 0}."
            )
        if proposals:
            answer += " I prepared typed action proposals; none have been executed."
        return answer, tuple(proposals), evidence

    @staticmethod
    def _proposal(
        context: DirectorContext, command_type: str, rationale: str
    ) -> DirectorActionProposal:
        return DirectorActionProposal(
            proposal_id=f"proposal:{uuid4()}",
            command_type=command_type,
            target=context.project_id,
            payload={},
            rationale=rationale,
        )


class DirectorChatService:
    def __init__(
        self,
        snapshot_provider: Callable[[], CommandCenterSnapshot],
        *,
        incident_provider: Callable[[str], IncidentCase] | None = None,
        responder: DirectorResponder | None = None,
        message_sink: Callable[[DirectorChatMessage], None] | None = None,
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.incident_provider = incident_provider
        self.responder = responder or DeterministicGroundedDirectorResponder()
        self.message_sink = message_sink
        self.context_builder = DirectorContextBuilder()
        self._history: dict[str, list[DirectorChatMessage]] = {}

    def ask(self, request: DirectorChatRequest, *, actor_id: str) -> DirectorChatResponse:
        snapshot = self.snapshot_provider()
        incident = None
        if request.scope is CommandCenterScope.INCIDENT:
            if self.incident_provider is None or request.incident_id is None:
                raise KeyError("incident provider unavailable")
            incident = self.incident_provider(request.incident_id)
        context = self.context_builder.build(
            snapshot,
            scope=request.scope,
            incident_id=request.incident_id,
            source_ids=("PROJECT_PIPELINE_LIVE_PROJECTION",),
            incident=incident,
        )
        conversation_id = request.conversation_id or f"conversation:{uuid4()}"
        user = DirectorChatMessage(
            message_id=f"message:{uuid4()}",
            conversation_id=conversation_id,
            role=DirectorMessageRole.USER,
            content=request.message,
            actor_id=actor_id,
            scope=request.scope,
            project_id=snapshot.project_id,
            incident_id=request.incident_id,
            snapshot_fingerprint=snapshot.fingerprint,
        )
        answer, proposals, evidence_ids = self.responder.respond(context, request.message)
        assistant = DirectorChatMessage(
            message_id=f"message:{uuid4()}",
            conversation_id=conversation_id,
            role=DirectorMessageRole.ASSISTANT,
            content=answer,
            scope=request.scope,
            project_id=snapshot.project_id,
            incident_id=request.incident_id,
            snapshot_fingerprint=snapshot.fingerprint,
            evidence_ids=evidence_ids,
        )
        history = self._history.setdefault(conversation_id, [])
        history.extend((user, assistant))
        if self.message_sink is not None:
            self.message_sink(user)
            self.message_sink(assistant)
        return DirectorChatResponse(
            conversation_id=conversation_id,
            request_message_id=user.message_id,
            response_message=assistant,
            context=context,
            proposals=proposals,
        )

    def history(self, conversation_id: str) -> tuple[DirectorChatMessage, ...]:
        return tuple(self._history.get(conversation_id, ()))


class CommandCenterControlGateway:
    """The operator surface can request commands but cannot mutate canonical state directly."""

    def __init__(
        self, processor: CommandProcessor, authorize: Callable[[CommandEnvelope], bool]
    ) -> None:
        self.processor = processor
        self.authorize = authorize

    def execute(self, command: CommandEnvelope) -> CommandResult:
        if command.action_intent is None:
            raise PermissionError("operator mutations require a typed ActionIntent")
        if not self.authorize(command):
            raise PermissionError("command denied by authorization/policy boundary")
        return self.processor.execute(command)
