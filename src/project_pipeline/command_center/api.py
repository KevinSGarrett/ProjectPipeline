from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse

from project_pipeline.command_center.application import CommandCenterApplicationProjection
from project_pipeline.command_center.autonomy_director import PersistentAutonomyDirector
from project_pipeline.command_center.director import (
    CommandCenterControlGateway,
    DirectorChatService,
    DirectorContextBuilder,
)
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.incidents import IncidentManager
from project_pipeline.command_center.models import (
    CommandCenterScope,
    CommandCenterSnapshot,
    DirectorChatRequest,
    IncidentVerificationRequest,
)
from project_pipeline.command_center.notifications import NotificationDeliveryService
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.contracts import CommandEnvelope
from project_pipeline.domain.control import ControlSnapshot


@dataclass(frozen=True, slots=True)
class CommandCenterAuth:
    token_validator: Callable[[str], str | None]

    def authenticate(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise PermissionError("bearer authentication required")
        token = authorization[7:].strip()
        actor = self.token_validator(token)
        if not actor:
            raise PermissionError("invalid bearer token")
        return actor

    @classmethod
    def deny_all(cls) -> CommandCenterAuth:
        return cls(lambda _token: None)


def create_command_center_app(
    *,
    snapshot_provider: Callable[[], CommandCenterSnapshot],
    event_broker: RealtimeEventBroker,
    inbox: AttentionNotificationBroker,
    control_gateway: CommandCenterControlGateway | None = None,
    application_provider: Callable[[], CommandCenterApplicationProjection] | None = None,
    director_chat: DirectorChatService | None = None,
    incident_manager: IncidentManager | None = None,
    notification_service: NotificationDeliveryService | None = None,
    auth: CommandCenterAuth | None = None,
    autonomy_director: PersistentAutonomyDirector | None = None,
    control_provider: Callable[[], ControlSnapshot] | None = None,
):
    app = FastAPI(title="Project Pipeline Command Center API", version="1.1.0")
    auth = auth or CommandCenterAuth.deny_all()
    director = DirectorContextBuilder()

    def principal(authorization: str | None = Header(default=None)) -> str:
        try:
            return auth.authenticate(authorization)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "authority": "PROJECT_PIPELINE"}

    @app.get("/api/v1/command-center/capabilities")
    def capabilities(_actor: str = Depends(principal)) -> dict[str, Any]:
        return {
            "canonical_authority": "PROJECT_PIPELINE",
            "ui_state_authoritative": False,
            "transports": ["http", "sse", "websocket"],
            "application_projection": application_provider is not None,
            "director_chat": director_chat is not None,
            "persistent_autonomy_director": autonomy_director is not None,
            "incident_management": incident_manager is not None,
            "notification_delivery": {
                "configured": notification_service is not None,
                "remote_enabled": bool(
                    notification_service and notification_service.policy.remote_channels_enabled
                ),
                "canonical_broker": "PROJECT_PIPELINE",
            },
            "replay_cursor": "EventEnvelope.sequence",
            "ag_ui": {
                "compatible": True,
                "internal_event_contract": "EventEnvelope",
                "event_types": [
                    "RUN_STARTED",
                    "RUN_FINISHED",
                    "RUN_ERROR",
                    "TEXT_MESSAGE_START",
                    "TEXT_MESSAGE_CONTENT",
                    "TEXT_MESSAGE_END",
                    "STATE_SNAPSHOT",
                    "CUSTOM",
                ],
            },
        }

    @app.get("/api/v1/command-center/status")
    def status(_actor: str = Depends(principal)) -> dict[str, Any]:
        return snapshot_provider().model_dump(mode="json")

    @app.get("/api/v1/command-center/application")
    def application(_actor: str = Depends(principal)) -> dict[str, Any]:
        if application_provider is None:
            raise HTTPException(
                status_code=503, detail="application projection provider not configured"
            )
        return application_provider().model_dump(mode="json")

    @app.get("/api/v1/command-center/inbox")
    def operator_inbox(_actor: str = Depends(principal)) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in inbox.list_open()]

    @app.post("/api/v1/command-center/inbox/{inbox_id}/ack")
    def ack(inbox_id: str, _actor: str = Depends(principal)) -> dict[str, Any]:
        try:
            return inbox.acknowledge(inbox_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="inbox item not found") from exc

    @app.post("/api/v1/command-center/inbox/{inbox_id}/dispatch")
    def dispatch_notification(
        inbox_id: str,
        local_hour: int = Query(ge=0, le=23),
        _actor: str = Depends(principal),
    ) -> dict[str, Any]:
        if notification_service is None:
            raise HTTPException(
                status_code=503, detail="notification delivery service not configured"
            )
        try:
            item = next(value for value in inbox.list_open() if value.inbox_id == inbox_id)
        except StopIteration as exc:
            raise HTTPException(status_code=404, detail="open inbox item not found") from exc
        action_link = f"/command-center?inbox={inbox_id}"
        return notification_service.dispatch(
            item, local_hour=local_hour, action_link=action_link
        ).model_dump(mode="json")

    @app.get("/api/v1/command-center/timeline")
    def timeline(
        after_sequence: int = 0,
        limit: int = Query(default=200, ge=1, le=1000),
        _actor: str = Depends(principal),
    ) -> dict[str, Any]:
        return event_broker.page(after_sequence=after_sequence, limit=limit).model_dump(mode="json")

    @app.get("/api/v1/command-center/events")
    def sse(after_sequence: int = 0, follow: bool = False, _actor: str = Depends(principal)):
        async def stream():
            if not follow:
                for event in event_broker.page(after_sequence=after_sequence, limit=1000).events:
                    yield event_broker.sse(event)
                return
            async for event in event_broker.subscribe(after_sequence=after_sequence):
                yield event_broker.sse(event)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.websocket("/api/v1/command-center/ws")
    async def websocket_events(
        websocket: WebSocket, after_sequence: int = 0, token: str | None = None
    ):
        query_token = token or websocket.query_params.get("token")
        authorization = websocket.headers.get("authorization")
        if not authorization and query_token:
            authorization = f"Bearer {query_token}"
        try:
            actor = auth.authenticate(authorization)
        except PermissionError:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            async for event in event_broker.subscribe(after_sequence=after_sequence):
                await websocket.send_json({"actor": actor, "event": event.model_dump(mode="json")})
        except WebSocketDisconnect:
            return

    @app.get("/api/v1/director/autonomy")
    def autonomy_status(_actor: str = Depends(principal)) -> dict[str, Any]:
        if autonomy_director is None:
            raise HTTPException(
                status_code=503,
                detail="Persistent Autonomy Director not configured",
            )
        return autonomy_director.projection()

    @app.post("/api/v1/director/autonomy/select")
    def autonomy_select(_actor: str = Depends(principal)) -> dict[str, Any]:
        if autonomy_director is None or control_provider is None:
            raise HTTPException(
                status_code=503,
                detail="Persistent Autonomy Director not configured",
            )
        decision = autonomy_director.select_next_work(control_provider())
        return {
            "decision": decision.as_dict(),
            "projection": autonomy_director.projection(),
        }

    @app.post("/api/v1/director/autonomy/recover")
    def autonomy_recover(_actor: str = Depends(principal)) -> dict[str, Any]:
        if autonomy_director is None:
            raise HTTPException(
                status_code=503,
                detail="Persistent Autonomy Director not configured",
            )
        return autonomy_director.recover()

    @app.post("/api/v1/director/context")
    def director_context(
        scope: CommandCenterScope = CommandCenterScope.PROJECT,
        incident_id: str | None = None,
        _actor: str = Depends(principal),
    ) -> dict[str, Any]:
        try:
            incident = (
                incident_manager.get(incident_id)
                if incident_manager is not None and incident_id
                else None
            )
            return director.build(
                snapshot_provider(),
                scope=scope,
                incident_id=incident_id,
                source_ids=("PROJECT_PIPELINE_LIVE_PROJECTION",),
                incident=incident,
            ).model_dump(mode="json")
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/director/chat")
    def director_chat_endpoint(
        request: DirectorChatRequest, actor: str = Depends(principal)
    ) -> dict[str, Any]:
        if director_chat is None:
            raise HTTPException(status_code=503, detail="Director Chat service not configured")
        try:
            return director_chat.ask(request, actor_id=actor).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident context not found") from exc

    @app.get("/api/v1/director/conversations/{conversation_id}")
    def director_history(
        conversation_id: str, _actor: str = Depends(principal)
    ) -> list[dict[str, Any]]:
        if director_chat is None:
            raise HTTPException(status_code=503, detail="Director Chat service not configured")
        return [item.model_dump(mode="json") for item in director_chat.history(conversation_id)]

    @app.get("/api/v1/command-center/incidents")
    def incidents(_actor: str = Depends(principal)) -> list[dict[str, Any]]:
        if incident_manager is None:
            raise HTTPException(status_code=503, detail="incident manager not configured")
        return [item.model_dump(mode="json") for item in incident_manager.list_active()]

    @app.post("/api/v1/command-center/incidents/{incident_id}/ack")
    def incident_ack(incident_id: str, _actor: str = Depends(principal)) -> dict[str, Any]:
        if incident_manager is None:
            raise HTTPException(status_code=503, detail="incident manager not configured")
        try:
            return incident_manager.acknowledge(incident_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.post("/api/v1/command-center/incidents/{incident_id}/recovery/start")
    def incident_recovery_start(
        incident_id: str, _actor: str = Depends(principal)
    ) -> dict[str, Any]:
        if incident_manager is None:
            raise HTTPException(status_code=503, detail="incident manager not configured")
        try:
            return incident_manager.begin_recovery(incident_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.post("/api/v1/command-center/incidents/{incident_id}/verify")
    def incident_verify(
        incident_id: str,
        verification: IncidentVerificationRequest,
        _actor: str = Depends(principal),
    ) -> dict[str, Any]:
        if incident_manager is None:
            raise HTTPException(status_code=503, detail="incident manager not configured")
        try:
            return incident_manager.verify(
                incident_id,
                verification_results=verification.verification_results,
                stale_assumptions_invalidated=verification.stale_assumptions_invalidated,
                reconciliation_complete=verification.reconciliation_complete,
            ).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.post("/api/v1/command-center/incidents/{incident_id}/resolve")
    def incident_resolve(incident_id: str, _actor: str = Depends(principal)) -> dict[str, Any]:
        if incident_manager is None:
            raise HTTPException(status_code=503, detail="incident manager not configured")
        try:
            return incident_manager.resolve(incident_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/command-center/control")
    def control(command: CommandEnvelope, actor: str = Depends(principal)) -> dict[str, Any]:
        if control_gateway is None:
            raise HTTPException(status_code=503, detail="control gateway not configured")
        if command.actor_id != actor:
            raise HTTPException(
                status_code=403, detail="authenticated actor does not match command actor"
            )
        try:
            return control_gateway.execute(command).model_dump(mode="json")
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return app
