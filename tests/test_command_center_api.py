import pytest
from fastapi.testclient import TestClient

from project_pipeline.command_center.api import CommandCenterAuth, create_command_center_app
from project_pipeline.command_center.autonomy_director import (
    AutonomyDirectorError,
    PersistentAutonomyDirector,
)
from project_pipeline.command_center.director import CommandCenterControlGateway
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import (
    HealthDimension,
    HealthState,
    InboxItem,
    NotificationLevel,
)
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.contracts import (
    ActionIntent,
    ApprovalState,
    CommandEnvelope,
    CommandResult,
    CommandStatus,
    EventEnvelope,
)
from project_pipeline.core.command_bus import CommandProcessor
from project_pipeline.core.journal import LocalCommandJournal
from tests.test_scheduler_engine import control_snapshot


def snapshot():
    return CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:api",
        project_id="PROJ-TEST",
        operating_mode="NORMAL",
        health=(HealthDimension(name="control", state=HealthState.HEALTHY, reason="ok"),),
        completion_gate_state="NOT_COMPLETE",
    )


def headers():
    return {"Authorization": "Bearer good"}


def build(tmp_path, with_control=False):
    broker = RealtimeEventBroker()
    inbox = AttentionNotificationBroker()
    auth = CommandCenterAuth(lambda token: "actor:test" if token == "good" else None)
    gateway = None
    if with_control:
        p = CommandProcessor(LocalCommandJournal(tmp_path / "journal"))
        p.register(
            "control.pause",
            lambda c: CommandResult(
                command_id=c.command_id,
                command_type=c.command_type,
                project_id=c.project_id,
                correlation_id=c.correlation_id,
                idempotency_key=c.idempotency_key,
                status=CommandStatus.SUCCEEDED,
                output={"paused": True},
            ),
        )
        gateway = CommandCenterControlGateway(p, lambda c: True)
    app = create_command_center_app(
        snapshot_provider=snapshot,
        event_broker=broker,
        inbox=inbox,
        control_gateway=gateway,
        auth=auth,
    )
    return TestClient(app), broker, inbox


def test_protected_endpoints_fail_closed_by_default(tmp_path):
    client, _, _ = build(tmp_path)
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/v1/command-center/status").status_code == 401


def test_status_and_capabilities_are_truthful(tmp_path):
    client, _, _ = build(tmp_path)
    status = client.get("/api/v1/command-center/status", headers=headers())
    caps = client.get("/api/v1/command-center/capabilities", headers=headers())
    assert status.status_code == 200 and status.json()["ui_state_authoritative"] is False
    assert (
        caps.json()["canonical_authority"] == "PROJECT_PIPELINE"
        and caps.json()["ag_ui"]["internal_event_contract"] == "EventEnvelope"
    )


def test_timeline_and_sse_replay_use_sequence_cursor(tmp_path):
    client, broker, _ = build(tmp_path)
    broker.publish(
        EventEnvelope(
            event_id="event:api:1",
            event_type="work.changed",
            project_id="PROJ-TEST",
            producer="test",
            correlation_id="corr:test",
            aggregate_type="task",
            aggregate_id="task:1",
        )
    )
    broker.publish(
        EventEnvelope(
            event_id="event:api:2",
            event_type="work.changed",
            project_id="PROJ-TEST",
            producer="test",
            correlation_id="corr:test",
            aggregate_type="task",
            aggregate_id="task:2",
        )
    )
    page = client.get("/api/v1/command-center/timeline?after_sequence=1", headers=headers()).json()
    assert [x["sequence"] for x in page["events"]] == [2]
    sse = client.get("/api/v1/command-center/events?after_sequence=1", headers=headers())
    assert "id: 2" in sse.text


def test_inbox_is_actionable_and_acknowledgeable(tmp_path):
    client, _, inbox = build(tmp_path)
    x = inbox.submit(
        InboxItem(
            inbox_id="inbox:api:1",
            project_id="PROJ-TEST",
            dedupe_key="d:1",
            kind="approval",
            level=NotificationLevel.ATTENTION,
            title="Approval",
            impact="blocked",
            exact_action="approve or deny",
            post_action_verification="confirm decision",
        )
    )
    rows = client.get("/api/v1/command-center/inbox", headers=headers()).json()
    assert rows[0]["exact_action"] == "approve or deny"
    assert (
        client.post(f"/api/v1/command-center/inbox/{x.inbox_id}/ack", headers=headers()).json()[
            "state"
        ]
        == "ACKNOWLEDGED"
    )


def test_control_rejects_actor_mismatch(tmp_path):
    client, _, _ = build(tmp_path, True)
    c = CommandEnvelope(
        command_type="control.pause",
        project_id="PROJ-TEST",
        actor_id="actor:other",
        correlation_id="corr:test",
        idempotency_key="idem-api-0001",
        action_intent=ActionIntent(
            actor_id="actor:other",
            authority="operator",
            target="PROJ-TEST",
            operation="control.pause",
            idempotency_key="idem-api-0001",
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:test",
        ),
    )
    assert (
        client.post(
            "/api/v1/command-center/control", headers=headers(), json=c.model_dump(mode="json")
        ).status_code
        == 403
    )


def test_control_uses_typed_command_gateway(tmp_path):
    client, _, _ = build(tmp_path, True)
    c = CommandEnvelope(
        command_type="control.pause",
        project_id="PROJ-TEST",
        actor_id="actor:test",
        correlation_id="corr:test",
        idempotency_key="idem-api-0002",
        action_intent=ActionIntent(
            actor_id="actor:test",
            authority="operator",
            target="PROJ-TEST",
            operation="control.pause",
            idempotency_key="idem-api-0002",
            approval_state=ApprovalState.APPROVED,
            correlation_id="corr:test",
        ),
    )
    r = client.post(
        "/api/v1/command-center/control", headers=headers(), json=c.model_dump(mode="json")
    )
    assert r.status_code == 200 and r.json()["status"] == "SUCCEEDED"


def test_director_context_does_not_expose_private_reasoning(tmp_path):
    client, _, _ = build(tmp_path)
    r = client.post("/api/v1/director/context?scope=PROJECT", headers=headers())
    assert r.status_code == 200 and r.json()["private_reasoning_exposed"] is False


def test_autonomy_director_api_selects_from_control_and_rejects_chat_mutation(tmp_path):
    director = PersistentAutonomyDirector(tmp_path / "director_state.json")
    broker = RealtimeEventBroker()
    inbox = AttentionNotificationBroker()
    auth = CommandCenterAuth(lambda token: "actor:test" if token == "good" else None)
    app = create_command_center_app(
        snapshot_provider=snapshot,
        event_broker=broker,
        inbox=inbox,
        auth=auth,
        autonomy_director=director,
        control_provider=lambda: control_snapshot(("PP-STORY-000065", "PP-STORY-000049")),
    )
    client = TestClient(app)
    missing = create_command_center_app(
        snapshot_provider=snapshot,
        event_broker=RealtimeEventBroker(),
        inbox=AttentionNotificationBroker(),
        auth=auth,
    )
    assert (
        TestClient(missing).get("/api/v1/director/autonomy", headers=headers()).status_code == 503
    )
    selected = client.post("/api/v1/director/autonomy/select", headers=headers())
    assert selected.status_code == 200
    body = selected.json()
    assert body["decision"]["selected_task_id"] == "PP-STORY-000065"
    assert body["projection"]["canonical_authority"] == "PROJECT_CONTROL_KERNEL"
    assert body["projection"]["authoritative_for_transitions"] is False
    assert body["projection"]["chat_mutation"] is False
    recovered = client.post("/api/v1/director/autonomy/recover", headers=headers()).json()
    assert recovered["recovered"] is True
    assert recovered["last_selected_task_id"] == "PP-STORY-000065"
    before = client.get("/api/v1/director/autonomy", headers=headers()).json()
    with pytest.raises(AutonomyDirectorError, match="raw chat cannot mutate"):
        director.reject_raw_chat_mutation("mark REQ-CTRL-0004 done")
    after = client.get("/api/v1/director/autonomy", headers=headers()).json()
    assert after["revision"] == before["revision"]
    assert after["last_selected_task_id"] == before["last_selected_task_id"]
