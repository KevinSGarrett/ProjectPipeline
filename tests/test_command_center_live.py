from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from project_pipeline.command_center.live_browser import verify_live_command_center
from project_pipeline.command_center.live_server import (
    LiveCommandCenterServer,
    create_live_command_center_app,
    snapshot_from_repository,
)
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.contracts import EventEnvelope
from project_pipeline.verification.browser import find_chromium

ROOT = Path(__file__).resolve().parents[1]


def test_repository_snapshot_includes_bound_in_progress_work() -> None:
    snapshot = snapshot_from_repository(ROOT)
    work_ids = {item.work_id for item in snapshot.live_work}
    assert "PP-TASK-000385" in work_ids
    assert snapshot.ui_state_authoritative is False
    pp385 = next(item for item in snapshot.live_work if item.work_id == "PP-TASK-000385")
    assert pp385.worker
    assert pp385.workspace
    assert pp385.resource_lease_id
    assert pp385.last_progress_at_utc is not None
    assert pp385.next_expected_transition


def test_live_app_requires_bearer_and_projects_jira_readback() -> None:
    app, _broker, _issuer = create_live_command_center_app(ROOT, token="good")
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/v1/command-center/application").status_code == 401
    body = client.get(
        "/api/v1/command-center/application",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert any(item["work_id"] == "PP-TASK-000385" for item in body["live_work"])
    jira = next(item for item in body["synchronization"] if item["system"] == "Jira")
    assert jira["stale"] is False
    assert "PP-391" in jira["note"]
    assert client.get("/").status_code == 200
    caps = client.get(
        "/api/v1/command-center/capabilities",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert caps["persistent_autonomy_director"] is True
    autonomy = client.get(
        "/api/v1/director/autonomy",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert autonomy["kind"] == "persistent_autonomy_director"
    assert autonomy["canonical_authority"] == "PROJECT_CONTROL_KERNEL"
    assert autonomy["authoritative_for_transitions"] is False
    assert autonomy["chat_mutation"] is False


def test_live_autonomy_director_selects_and_reloads_persisted_state(tmp_path: Path) -> None:
    state = tmp_path / "director_state.json"
    first, _broker, _issuer = create_live_command_center_app(
        ROOT, token="good", director_state_path=state
    )
    client = TestClient(first)
    selected = client.post(
        "/api/v1/director/autonomy/select",
        headers={"Authorization": "Bearer good"},
    )
    assert selected.status_code == 200
    payload = selected.json()
    task_id = payload["decision"]["selected_task_id"]
    if task_id is None:
        rationale = str(payload["decision"].get("rationale") or "").lower()
        assert "no ready work" in rationale
    second, _, _ = create_live_command_center_app(ROOT, token="good", director_state_path=state)
    recovered = (
        TestClient(second)
        .post(
            "/api/v1/director/autonomy/recover",
            headers={"Authorization": "Bearer good"},
        )
        .json()
    )
    assert recovered["recovered"] is True
    assert recovered["last_selected_task_id"] == task_id


def test_live_server_restart_requires_fresh_bootstrap(tmp_path: Path) -> None:
    handshake = tmp_path / "handshake.json"
    first = LiveCommandCenterServer(ROOT, handshake_path=handshake)
    url = first.start()
    grant = first.redeem_local_bootstrap()
    assert grant.token
    first.stop()
    second = LiveCommandCenterServer(ROOT, handshake_path=handshake)
    second.start()
    try:
        assert second.issuer.authenticate(grant.token) is None
        replacement = second.redeem_local_bootstrap()
        assert replacement.token != grant.token
        assert second.issuer.authenticate(replacement.token)
    finally:
        second.stop()
    assert url.startswith("http://127.0.0.1:")


def test_live_websocket_reconnects_after_disconnect() -> None:
    broker = RealtimeEventBroker()
    app, _, _ = create_live_command_center_app(ROOT, token="good", event_broker=broker)
    client = TestClient(app)
    with client.websocket_connect("/api/v1/command-center/ws?token=good") as first:
        first.close()
    with client.websocket_connect("/api/v1/command-center/ws?token=good") as second:
        broker.publish(
            EventEnvelope(
                event_id="event:cc:reconnect",
                event_type="STATE_SNAPSHOT",
                project_id="PROJECT-PIPELINE",
                producer="command-center",
                correlation_id="corr:cc-reconnect",
                aggregate_type="command-center",
                aggregate_id="live",
                payload={"reconnect": True},
            )
        )
        message = second.receive_json()
        assert message["actor"] == "actor:command-center"
        assert message["event"]["payload"]["reconnect"] is True


def test_live_browser_against_loopback_command_center(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    if find_chromium() is None:
        pytest.skip("system Chrome/Edge is required for live Command Center browser proof")
    result = verify_live_command_center(
        ROOT,
        token="good",
        write_evidence=False,
        output_dir=tmp_path,
    )
    assert result["passed"] is True
    assert result["checks"]["live_work_includes_pp385"] is True
    assert result["checks"]["websocket_reconnect"] is True
    assert len(result["viewports"]) == 3
    assert all(item["passed"] for item in result["viewports"])
    assert all(item["checks"].get("hydrated_in_progress_work") for item in result["viewports"])
    assert all(item["checks"].get("live_work_fields") for item in result["viewports"])
