from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from project_pipeline.command_center.api import CommandCenterAuth, create_command_center_app
from project_pipeline.command_center.application import RepositoryApplicationProjectionBuilder
from project_pipeline.command_center.autonomy_director import (
    PersistentAutonomyDirector,
    default_state_path,
    evaluate_live_control,
)
from project_pipeline.command_center.desktop_session import (
    DesktopSessionError,
    EphemeralSessionIssuer,
    SessionGrant,
    current_os_identity,
    is_loopback_host,
    validate_bind_host,
)
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.incidents import IncidentManager
from project_pipeline.command_center.models import (
    CommandCenterSnapshot,
    HealthDimension,
    HealthState,
    LiveWorkItem,
    ReadinessMetric,
)
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.domain.control import ControlSnapshot
from project_pipeline.jira import load_issues

_uvicorn: Any
try:
    import uvicorn as _uvicorn
except ImportError:
    _uvicorn = None

_LIVE_CONTROL_LOCK = threading.Lock()


def _issue_progress_time(item: dict[str, Any]) -> datetime | None:
    observation = item.get("last_remote_observation")
    raw = observation.get("observed_at_utc") if isinstance(observation, dict) else None
    raw = raw or item.get("updated_at_utc")
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


def live_control_snapshot(root: Path) -> ControlSnapshot:
    with _LIVE_CONTROL_LOCK:
        return evaluate_live_control(root)


def snapshot_from_repository(root: Path) -> CommandCenterSnapshot:
    issues = load_issues(root)
    in_progress = [item for item in issues if item.get("state") == "IN_PROGRESS"]
    live_work = tuple(
        LiveWorkItem(
            work_id=str(item["local_id"]),
            title=str(item.get("title") or item["local_id"])[:300],
            state="IN_PROGRESS",
            owner=str(item.get("owner_required_capability") or "repository"),
            worker=str(item.get("owner_required_capability") or "repository"),
            workspace=(
                str((item.get("expected_file_locations") or [f"repository:{item['local_id']}"])[0])[
                    :512
                ]
            ),
            current_stage=str(item.get("implementation_state") or "UNKNOWN"),
            resource_lease_id=f"repo-claim:{item['local_id']}",
            last_progress_at_utc=_issue_progress_time(item),
            next_expected_transition=(
                "Complete acceptance criteria and attach evidence"
                if item.get("state") == "IN_PROGRESS"
                else None
            ),
        )
        for item in in_progress
    )
    implemented = sum(1 for item in issues if item.get("implementation_state") == "IMPLEMENTED")
    readiness_value = implemented / len(issues) if issues else 0.0
    return CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc-live-repository",
        project_id="PROJECT-PIPELINE",
        operating_mode="local-real",
        health=(
            HealthDimension(
                name="command-center",
                state=HealthState.HEALTHY,
                reason="loopback Command Center is serving repository-backed state",
            ),
        ),
        completion_gate_state="NOT_COMPLETE",
        completion_percent=round(readiness_value * 100, 2),
        readiness=(
            ReadinessMetric(
                metric_id="implementation",
                label="Implementation",
                value=readiness_value,
                basis="repository issue implementation_state",
            ),
        ),
        live_work=live_work,
        evidence_count=len(in_progress),
        context_summary={
            "source": "repository",
            "in_progress_count": len(in_progress),
            "user_action_required": False,
        },
    )


def create_live_command_center_app(
    root: Path,
    *,
    token: str | None = None,
    issuer: EphemeralSessionIssuer | None = None,
    event_broker: RealtimeEventBroker | None = None,
    director_state_path: Path | None = None,
) -> tuple[FastAPI, RealtimeEventBroker, EphemeralSessionIssuer]:
    root = root.resolve()
    broker = event_broker or RealtimeEventBroker()
    inbox = AttentionNotificationBroker()
    incidents = IncidentManager(inbox)
    builder = RepositoryApplicationProjectionBuilder(root)
    director = PersistentAutonomyDirector(director_state_path or default_state_path(root))
    session_issuer = issuer or EphemeralSessionIssuer(os_identity=current_os_identity())
    if token:
        session_issuer.seed_static_token(token, actor_id="actor:command-center")

    runtime_database = load_runtime_configuration(root).settings.database_path(root)
    app = create_command_center_app(
        snapshot_provider=lambda: snapshot_from_repository(root),
        event_broker=broker,
        inbox=inbox,
        application_provider=lambda: builder.build(snapshot_from_repository(root)),
        incident_manager=incidents,
        auth=CommandCenterAuth(session_issuer.authenticate),
        autonomy_director=director,
        control_provider=lambda: live_control_snapshot(root),
        repository_root=root,
        runtime_database=runtime_database,
    )
    preview = root / "apps/command_center/preview/index.html"

    def _preview_html() -> str:
        return preview.read_text(encoding="utf-8")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/", include_in_schema=False)
    def preview_index() -> HTMLResponse:
        return HTMLResponse(_preview_html())

    @app.get("/command-center", include_in_schema=False)
    def preview_alias() -> HTMLResponse:
        return HTMLResponse(_preview_html())

    @app.post("/api/v1/command-center/session/bootstrap")
    def session_bootstrap(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        peer = request.client.host if request.client is not None else ""
        if not is_loopback_host(peer):
            raise HTTPException(status_code=401, detail="bootstrap is loopback-only")
        try:
            grant = session_issuer.redeem(
                str(payload.get("nonce") or ""),
                peer_host=peer,
                os_identity=str(payload.get("os_identity") or ""),
            )
        except DesktopSessionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {
            "token": grant.token,
            "actor_id": grant.actor_id,
            "os_identity": grant.os_identity,
            "session_id": grant.session_id,
            "expires_at_utc": grant.expires_at_utc.isoformat(),
            "persist_secrets": False,
        }

    return app, broker, session_issuer


class LiveCommandCenterServer:
    def __init__(
        self,
        root: Path,
        *,
        token: str | None = None,
        issuer: EphemeralSessionIssuer | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        handshake_path: Path | None = None,
    ) -> None:
        bind_host = validate_bind_host(host)
        self.root = root.resolve()
        self.host = host
        self.issuer = issuer or EphemeralSessionIssuer(os_identity=current_os_identity())
        self.app, self.broker, self.issuer = create_live_command_center_app(
            self.root,
            token=token,
            issuer=self.issuer,
        )
        self.token = token
        self.handshake_path = handshake_path
        if _uvicorn is None:
            raise RuntimeError("uvicorn is required to serve the live Command Center")
        chosen = port
        if chosen == 0:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((bind_host, 0))
                chosen = int(probe.getsockname()[1])
        self._config = _uvicorn.Config(
            self.app, host=bind_host, port=chosen, log_level="error", access_log=False
        )
        self._server = _uvicorn.Server(self._config)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._config.port)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> str:
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{self.base_url}/healthz", timeout=1) as response:
                    if response.status == 200:
                        if self.handshake_path is not None:
                            self.issuer.write_handshake(self.handshake_path, url=self.base_url)
                        return self.base_url
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                time.sleep(0.05)
                continue
            time.sleep(0.05)
        raise RuntimeError("Command Center live server failed to start")

    def redeem_local_bootstrap(self) -> SessionGrant:
        return self.issuer.redeem(
            self.issuer.bootstrap_nonce,
            peer_host="127.0.0.1",
            os_identity=self.issuer.os_identity,
        )

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
