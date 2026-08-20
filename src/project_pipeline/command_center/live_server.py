from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

try:
    from uvicorn import Config, Server
except ImportError:
    Config = None
    Server = None

from project_pipeline.command_center.api import CommandCenterAuth, create_command_center_app
from project_pipeline.command_center.application import RepositoryApplicationProjectionBuilder
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
from project_pipeline.jira import load_issues


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
    token: str,
    event_broker: RealtimeEventBroker | None = None,
) -> tuple[FastAPI, RealtimeEventBroker]:
    root = root.resolve()
    broker = event_broker or RealtimeEventBroker()
    inbox = AttentionNotificationBroker()
    incidents = IncidentManager(inbox)
    builder = RepositoryApplicationProjectionBuilder(root)

    app = create_command_center_app(
        snapshot_provider=lambda: snapshot_from_repository(root),
        event_broker=broker,
        inbox=inbox,
        application_provider=lambda: builder.build(snapshot_from_repository(root)),
        incident_manager=incidents,
        auth=CommandCenterAuth(lambda value: "actor:command-center" if value == token else None),
    )
    preview = root / "apps/command_center/preview/index.html"

    def _hydrated_preview() -> str:
        html = preview.read_text(encoding="utf-8")
        bootstrap = (
            "<script>window.CC_LIVE_TOKEN="
            + json.dumps(token)
            + ";document.documentElement.dataset.liveToken='1';</script>"
        )
        if "</head>" in html:
            return html.replace("</head>", bootstrap + "</head>", 1)
        return bootstrap + html

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/", include_in_schema=False)
    def preview_index() -> HTMLResponse:
        return HTMLResponse(_hydrated_preview())

    @app.get("/command-center", include_in_schema=False)
    def preview_alias() -> HTMLResponse:
        return HTMLResponse(_hydrated_preview())

    return app, broker


class LiveCommandCenterServer:
    def __init__(self, root: Path, *, token: str, host: str = "127.0.0.1", port: int = 0) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Command Center live server is loopback-only")
        self.root = root.resolve()
        self.token = token
        self.host = host
        self.app, self.broker = create_live_command_center_app(self.root, token=token)
        if Config is None or Server is None:
            raise RuntimeError("uvicorn is required to serve the live Command Center")
        bind_host = "127.0.0.1" if host == "localhost" else host
        chosen = port
        if chosen == 0:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((bind_host, 0))
                chosen = int(probe.getsockname()[1])
        self._config = Config(
            self.app, host=bind_host, port=chosen, log_level="error", access_log=False
        )
        self._server = Server(self._config)
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
                        return self.base_url
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                time.sleep(0.05)
                continue
            time.sleep(0.05)
        raise RuntimeError("Command Center live server failed to start")

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
