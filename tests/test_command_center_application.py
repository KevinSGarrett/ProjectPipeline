import json
from pathlib import Path

from fastapi.testclient import TestClient

from project_pipeline.command_center import (
    AttentionNotificationBroker,
    CommandCenterAuth,
    CommandCenterProjectionService,
    HealthDimension,
    HealthState,
    RealtimeEventBroker,
    RepositoryApplicationProjectionBuilder,
    create_command_center_app,
    validate_command_center_application,
)
from project_pipeline.command_center.models import ReadinessMetric


def _snapshot():
    return CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:app:test",
        project_id="PROJECT-PIPELINE",
        operating_mode="NORMAL",
        health=(HealthDimension(name="control", state=HealthState.HEALTHY, reason="responsive"),),
        completion_gate_state="NOT_COMPLETE",
        completion_percent=62.0,
        readiness=(
            ReadinessMetric(
                metric_id="implementation",
                label="Implementation",
                value=0.62,
                basis="accepted scope",
            ),
            ReadinessMetric(
                metric_id="verification", label="Verification", value=0.79, basis="linked evidence"
            ),
        ),
        active_incident_ids=("INCIDENT-LOCAL-001",),
        budget_summary={"forecast_usd": 286},
        provider_summary={"OpenAI": {"state": "READY"}},
        context_summary={"freshness": 0.97},
    )


def test_repository_projection_is_explicitly_non_authoritative(project_root):
    projection = RepositoryApplicationProjectionBuilder(project_root).build(_snapshot())
    assert projection.canonical_authority == "PROJECT_PIPELINE"
    assert projection.ui_state_authoritative is False
    assert projection.project_id == "PROJECT-PIPELINE"
    assert projection.readiness["implementation"] == 62.0


def test_repository_projection_never_invents_remote_sync_or_approval_truth(project_root):
    projection = RepositoryApplicationProjectionBuilder(project_root).build(_snapshot())
    assert projection.approvals_detail_available is False
    assert projection.approvals_detail == ()
    assert {item.system for item in projection.synchronization} == {"Jira", "GitHub"}
    jira = next(item for item in projection.synchronization if item.system == "Jira")
    github = next(item for item in projection.synchronization if item.system == "GitHub")
    assert jira.mode != "LOCAL_ONLY"
    assert jira.stale is False
    assert "PP-391" in jira.note
    assert github.mode == "LOCAL_ONLY"
    assert github.stale is True
    assert all(item.remote_mutation_performed is False for item in projection.synchronization)
    assert projection.recovery_detail[0]["detail_state"] == "LIVE_PROVIDER_REQUIRED"


def test_application_graph_is_bounded_and_traceable(project_root):
    projection = RepositoryApplicationProjectionBuilder(project_root, max_graph_nodes=80).build(
        _snapshot()
    )
    assert len(projection.graph.nodes) <= 80
    assert any(node.kind == "requirement" for node in projection.graph.nodes)
    assert all(
        node.authoritative_path
        for node in projection.graph.nodes
        if node.kind in {"requirement", "jira", "evidence"}
    )
    node_ids = {node.node_id for node in projection.graph.nodes}
    assert all(
        edge.source in node_ids and edge.target in node_ids for edge in projection.graph.edges
    )


def test_application_projection_endpoint_is_authenticated_and_truthful(project_root):
    snapshot = _snapshot()

    def provider():
        return RepositoryApplicationProjectionBuilder(project_root).build(snapshot)

    app = create_command_center_app(
        snapshot_provider=lambda: snapshot,
        event_broker=RealtimeEventBroker(),
        inbox=AttentionNotificationBroker(),
        application_provider=provider,
        auth=CommandCenterAuth(lambda token: "actor:test" if token == "good" else None),
    )
    client = TestClient(app)
    assert client.get("/api/v1/command-center/application").status_code == 401
    response = client.get(
        "/api/v1/command-center/application", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["canonical_authority"] == "PROJECT_PIPELINE"
    assert body["ui_state_authoritative"] is False
    caps = client.get(
        "/api/v1/command-center/capabilities", headers={"Authorization": "Bearer good"}
    ).json()
    assert caps["application_projection"] is True


def test_application_endpoint_fails_closed_without_projection_provider():
    snapshot = _snapshot()
    app = create_command_center_app(
        snapshot_provider=lambda: snapshot,
        event_broker=RealtimeEventBroker(),
        inbox=AttentionNotificationBroker(),
        auth=CommandCenterAuth(lambda token: "actor:test" if token == "good" else None),
    )
    response = TestClient(app).get(
        "/api/v1/command-center/application", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 503


def test_command_center_application_repository_contract_is_clean(project_root):
    assert validate_command_center_application(project_root) == []


def test_tauri_cli_discovers_project_from_desktop_shell_not_command_center(project_root):
    desktop = Path(project_root) / "apps/desktop_shell"
    frontend = Path(project_root) / "apps/command_center"
    assert (desktop / "src-tauri/tauri.conf.json").is_file()
    assert list(frontend.rglob("tauri.conf.json")) == []
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    assert "run-tauri.mjs" in package["scripts"]["tauri:build"]
    runner = (frontend / "scripts/run-tauri.mjs").read_text(encoding="utf-8")
    assert "cwd: desktopRoot" in runner
    assert "TAURI_FRONTEND_PATH: frontendRoot" in runner
    assert "TAURI_APP_PATH" in runner
    tauri = json.loads((desktop / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    assert tauri["build"]["beforeBuildCommand"] == "npm run build"
    assert (desktop / "src-tauri" / tauri["build"]["frontendDist"]).resolve() == (
        frontend / "dist"
    ).resolve()
