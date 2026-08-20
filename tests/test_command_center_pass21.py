import json

import pytest
from fastapi.testclient import TestClient

from project_pipeline.command_center.api import CommandCenterAuth, create_command_center_app
from project_pipeline.command_center.director import DirectorChatService
from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.incidents import IncidentManager
from project_pipeline.command_center.models import (
    CommandCenterScope,
    DirectorChatRequest,
    HealthDimension,
    HealthState,
    InboxItem,
    IncidentState,
    NotificationDeliveryState,
    NotificationLevel,
    NotificationPolicy,
)
from project_pipeline.command_center.notifications import (
    NotificationDeliveryService,
    NtfyHttpNotificationAdapter,
)
from project_pipeline.command_center.persistence import CommandCenterStore
from project_pipeline.command_center.projections import CommandCenterProjectionService
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.domain.resilience import ExternalPreconditionIncident, FailureDomain
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


def snapshot():
    return CommandCenterProjectionService().build_snapshot(
        snapshot_id="cc:pass21",
        project_id="PROJ-TEST",
        operating_mode="NORMAL",
        health=(
            HealthDimension(
                name="control",
                state=HealthState.HEALTHY,
                reason="canonical state healthy",
                evidence_ids=("EVID-TEST-1",),
            ),
        ),
        completion_gate_state="NOT_COMPLETE",
        completion_percent=78.5,
        active_incident_ids=("INCIDENT-AAAAAAAAAAAAAAAAAAAA",),
    )


def incident():
    return ExternalPreconditionIncident(
        incident_id="INCIDENT-AAAAAAAAAAAAAAAAAAAA",
        failure_domain=FailureDomain.API,
        summary="Remote provider credentials require human repair",
        autonomous_resolution_action="Rotate the provider credential and confirm the health check succeeds.",
        unaffected_work=("local deterministic validation",),
        blocked_work=("remote provider execution", "provider-backed review"),
        verification_steps=("credential validates", "provider health check passes"),
        stale_assumptions_to_invalidate=("provider credential remains valid",),
    )


def inbox_item(level=NotificationLevel.URGENT):
    return InboxItem(
        inbox_id="inbox:pass21:1",
        project_id="PROJ-TEST",
        dedupe_key="pass21:incident:1",
        kind="incident",
        level=level,
        title="Operator repair required",
        impact="Remote provider work is blocked.",
        exact_action="Rotate the credential.",
        post_action_verification="Confirm provider health.",
        critical_path=True,
        blocked_tasks=2,
    )


def test_director_chat_is_grounded_and_never_mutates_from_raw_text():
    canonical = snapshot()
    service = DirectorChatService(lambda: canonical)
    result = service.ask(
        DirectorChatRequest(
            message="What is the current project state?", scope=CommandCenterScope.PROJECT
        ),
        actor_id="actor:test",
    )
    assert result.context.snapshot_fingerprint == canonical.fingerprint
    assert result.response_message.snapshot_fingerprint == canonical.fingerprint
    assert "health=HEALTHY" in result.response_message.content
    assert result.private_reasoning_exposed is False
    assert result.raw_text_may_mutate_state is False
    assert result.canonical_authority == "PROJECT_PIPELINE"
    assert len(service.history(result.conversation_id)) == 2


def test_director_chat_prepares_typed_confirmation_required_action_proposal_only():
    service = DirectorChatService(snapshot)
    result = service.ask(
        DirectorChatRequest(
            message="Pause new work while I investigate", scope=CommandCenterScope.PROJECT
        ),
        actor_id="actor:test",
    )
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert proposal.command_type == "project.pause_new_work"
    assert proposal.requires_confirmation is True
    assert proposal.executes_automatically is False
    assert "none have been executed" in result.response_message.content.lower()


def test_director_incident_scope_requires_canonical_incident_context():
    broker = AttentionNotificationBroker()
    manager = IncidentManager(broker)
    case = manager.open(incident(), project_id="PROJ-TEST")
    service = DirectorChatService(snapshot, incident_provider=manager.get)
    result = service.ask(
        DirectorChatRequest(
            message="What exactly do I need to do?",
            scope=CommandCenterScope.INCIDENT,
            incident_id=case.incident.incident_id,
        ),
        actor_id="actor:test",
    )
    assert case.incident.autonomous_resolution_action in result.response_message.content
    assert result.context.facts["incident"]["state"] == "OPEN"
    assert result.context.incident_id == case.incident.incident_id


def test_incident_lifecycle_requires_verified_repair_before_resolution():
    broker = AttentionNotificationBroker()
    manager = IncidentManager(broker)
    case = manager.open(incident(), project_id="PROJ-TEST", evidence_ids=("EVID-TEST-INC",))
    assert case.state is IncidentState.OPEN
    inbox = broker.list_open()[0]
    assert inbox.exact_action == f"Autonomous recheck: {incident().autonomous_resolution_action}"
    assert "credential validates" in inbox.post_action_verification
    assert inbox.blocked_tasks == 2

    acknowledged = manager.acknowledge(case.incident.incident_id)
    assert acknowledged.state is IncidentState.ACKNOWLEDGED
    recovering = manager.begin_recovery(case.incident.incident_id)
    assert recovering.state is IncidentState.RECOVERING

    failed = manager.verify(
        case.incident.incident_id,
        verification_results={"credential": True, "health": False},
        stale_assumptions_invalidated=True,
        reconciliation_complete=True,
    )
    assert failed.state is IncidentState.RECOVERING
    with pytest.raises(ValueError, match="cannot resolve"):
        manager.resolve(case.incident.incident_id)

    verified = manager.verify(
        case.incident.incident_id,
        verification_results={"credential": True, "health": True},
        stale_assumptions_invalidated=True,
        reconciliation_complete=True,
    )
    assert verified.state is IncidentState.VERIFIED
    resolved = manager.resolve(case.incident.incident_id)
    assert resolved.state is IncidentState.RESOLVED
    assert not manager.list_active()
    assert broker.list_open() == ()


def test_incident_open_is_idempotent_until_resolved():
    broker = AttentionNotificationBroker()
    manager = IncidentManager(broker)
    first = manager.open(incident(), project_id="PROJ-TEST")
    second = manager.open(incident(), project_id="PROJ-TEST")
    assert second.incident.incident_id == first.incident.incident_id
    assert second.inbox_id == first.inbox_id
    assert len(broker.list_open()) == 1


class FakeAdapter:
    adapter_id = "apprise"
    remote = True

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def deliver(self, item, *, action_link=None):
        self.calls.append((item.inbox_id, action_link))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_notification_delivery_keeps_project_pipeline_as_broker_and_remote_default_off():
    broker = AttentionNotificationBroker()
    item = broker.submit(inbox_item(NotificationLevel.URGENT))
    service = NotificationDeliveryService(broker)
    result = service.dispatch(item, local_hour=12, action_link="/command-center?inbox=x")
    assert result.canonical_broker == "PROJECT_PIPELINE"
    assert result.remote_delivery_enabled is False
    assert "remote" not in result.decision.channels
    by_channel = {attempt.channel: attempt for attempt in result.deliveries}
    assert by_channel["operator_inbox"].state is NotificationDeliveryState.DELIVERED
    assert (
        by_channel["windows_notification"].state is NotificationDeliveryState.CLIENT_ACTION_REQUIRED
    )
    assert by_channel["windows_notification"].adapter_id == "tauri-client"


def test_notification_quiet_hours_suppress_attention_desktop_delivery():
    broker = AttentionNotificationBroker()
    item = broker.submit(inbox_item(NotificationLevel.ATTENTION))
    result = NotificationDeliveryService(broker).dispatch(item, local_hour=23)
    assert result.decision.suppressed is True
    assert result.decision.suppression_reason == "quiet_hours_nonurgent"
    assert result.decision.channels == ("operator_inbox",)


def test_remote_adapter_retries_then_delivers_and_deduplicates():
    policy = NotificationPolicy(remote_channels_enabled=True)
    broker = AttentionNotificationBroker(policy)
    item = broker.submit(inbox_item(NotificationLevel.CRITICAL))
    adapter = FakeAdapter([False, True])
    service = NotificationDeliveryService(
        broker,
        policy=policy,
        adapters={"apprise": adapter},
        max_attempts=3,
        retry_backoff_seconds=10,
    )
    first = service.dispatch(item, local_hour=12, action_link="/command-center?inbox=x")
    first_remote = next(x for x in first.deliveries if x.channel == "remote")
    assert first_remote.state is NotificationDeliveryState.RETRY_SCHEDULED
    assert first_remote.attempt_number == 1
    assert first_remote.next_retry_at_utc is not None

    second = service.dispatch(item, local_hour=12, action_link="/command-center?inbox=x")
    second_remote = next(x for x in second.deliveries if x.channel == "remote")
    assert second_remote.state is NotificationDeliveryState.DELIVERED
    assert second_remote.attempt_number == 2

    third = service.dispatch(item, local_hour=12, action_link="/command-center?inbox=x")
    third_remote = next(x for x in third.deliveries if x.channel == "remote")
    assert third_remote.state is NotificationDeliveryState.DUPLICATE_SUPPRESSED
    assert len(adapter.calls) == 2


def test_remote_adapter_failure_exposes_category_not_secret_message():
    policy = NotificationPolicy(remote_channels_enabled=True)
    broker = AttentionNotificationBroker(policy)
    item = broker.submit(inbox_item(NotificationLevel.URGENT))
    adapter = FakeAdapter([RuntimeError("secret-token-should-not-leak")])
    result = NotificationDeliveryService(
        broker, policy=policy, adapters={"apprise": adapter}, max_attempts=1
    ).dispatch(item, local_hour=12)
    remote = next(x for x in result.deliveries if x.channel == "remote")
    assert remote.state is NotificationDeliveryState.FAILED
    assert remote.error_category == "RuntimeError"
    assert "secret-token-should-not-leak" not in remote.model_dump_json()


def test_ntfy_http_adapter_uses_http_json_action_link_and_idempotency_header():
    captured = {}

    def transport(url, body, headers):
        captured.update(url=url, payload=json.loads(body.decode("utf-8")), headers=headers)
        return 200

    adapter = NtfyHttpNotificationAdapter(
        "https://ntfy.example.invalid", "project-pipeline", transport=transport
    )
    assert (
        adapter.deliver(inbox_item(), action_link="https://localhost/command-center?inbox=1")
        is True
    )
    assert captured["url"] == "https://ntfy.example.invalid"
    assert captured["payload"]["topic"] == "project-pipeline"
    assert captured["payload"]["click"] == "https://localhost/command-center?inbox=1"
    assert captured["headers"]["Idempotency-Key"] == "inbox:pass21:1"


def test_command_center_store_persists_pass21_artifacts(tmp_path, project_root):
    broker = AttentionNotificationBroker(NotificationPolicy(remote_channels_enabled=True))
    with CommandCenterStore(tmp_path / "cc.db", project_root) as store:
        manager = IncidentManager(broker, case_sink=store.save_incident_case)
        case = manager.open(incident(), project_id="PROJ-TEST")
        chat = DirectorChatService(
            snapshot, incident_provider=manager.get, message_sink=store.save_director_message
        )
        response = chat.ask(
            DirectorChatRequest(
                message="What is blocked?",
                scope=CommandCenterScope.INCIDENT,
                incident_id=case.incident.incident_id,
            ),
            actor_id="actor:test",
        )
        service = NotificationDeliveryService(broker, delivery_sink=store.save_delivery)
        service.dispatch(broker.list_open()[0], local_hour=12)
        status = store.status()
        assert status["command_center_director_messages"] == 2
        assert status["command_center_incident_cases"] == 1
        assert status["command_center_notification_deliveries"] >= 2
        assert response.context.incident_id == case.incident.incident_id
        assert SQLiteMigrationRunner(store.db, project_root).status().latest_applied == "PPDB-0025"


def test_ppdb_0017_rolls_back_without_removing_pass19_command_center_schema(tmp_path, project_root):
    import sqlite3

    conn = sqlite3.connect(tmp_path / "m.db")
    runner = SQLiteMigrationRunner(conn, project_root)
    runner.apply_all()
    assert runner.status().latest_applied == "PPDB-0025"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "command_center_director_messages" in tables and "command_center_events" in tables
    assert "lifecycle_portfolio_projects" in tables
    assert "autonomy_runtime_operations" in tables
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0024"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0023"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0022"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0021"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0020"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "lifecycle_portfolio_projects" in tables and "command_center_director_messages" in tables
    assert "autonomy_runtime_operations" in tables
    assert "qualification_runs" not in tables
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0019"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "lifecycle_portfolio_projects" in tables and "command_center_director_messages" in tables
    assert "autonomy_runtime_operations" not in tables
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0018"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "lifecycle_portfolio_projects" in tables and "command_center_director_messages" in tables
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0017"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert (
        "lifecycle_portfolio_projects" not in tables
        and "command_center_director_messages" in tables
    )
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0016"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "command_center_director_messages" not in tables
    assert "command_center_incident_cases" not in tables
    assert "command_center_notification_deliveries" not in tables
    assert "command_center_events" in tables


def test_pass21_api_endpoints_are_authenticated_grounded_and_stateful(tmp_path):
    event_broker = RealtimeEventBroker()
    broker = AttentionNotificationBroker()
    manager = IncidentManager(broker)
    case = manager.open(incident(), project_id="PROJ-TEST")
    chat = DirectorChatService(snapshot, incident_provider=manager.get)
    notification_service = NotificationDeliveryService(broker)
    auth = CommandCenterAuth(lambda token: "actor:test" if token == "good" else None)
    app = create_command_center_app(
        snapshot_provider=snapshot,
        event_broker=event_broker,
        inbox=broker,
        director_chat=chat,
        incident_manager=manager,
        notification_service=notification_service,
        auth=auth,
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer good"}
    assert (
        client.post(
            "/api/v1/director/chat", json={"message": "status", "scope": "PROJECT"}
        ).status_code
        == 401
    )

    response = client.post(
        "/api/v1/director/chat",
        headers=headers,
        json={"message": "Pause project", "scope": "PROJECT"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["raw_text_may_mutate_state"] is False
    assert body["proposals"][0]["executes_automatically"] is False
    conversation_id = body["conversation_id"]
    assert (
        len(client.get(f"/api/v1/director/conversations/{conversation_id}", headers=headers).json())
        == 2
    )

    rows = client.get("/api/v1/command-center/incidents", headers=headers).json()
    assert rows[0]["incident"]["incident_id"] == case.incident.incident_id
    assert (
        client.post(
            f"/api/v1/command-center/incidents/{case.incident.incident_id}/ack", headers=headers
        ).json()["state"]
        == "ACKNOWLEDGED"
    )
    assert (
        client.post(
            f"/api/v1/command-center/incidents/{case.incident.incident_id}/recovery/start",
            headers=headers,
        ).json()["state"]
        == "RECOVERING"
    )
    verify = client.post(
        f"/api/v1/command-center/incidents/{case.incident.incident_id}/verify",
        headers=headers,
        json={
            "verification_results": {"credential": True, "health": True},
            "stale_assumptions_invalidated": True,
            "reconciliation_complete": True,
        },
    )
    assert verify.status_code == 200 and verify.json()["state"] == "VERIFIED"
    assert (
        client.post(
            f"/api/v1/command-center/incidents/{case.incident.incident_id}/resolve", headers=headers
        ).json()["state"]
        == "RESOLVED"
    )


def test_notification_dispatch_api_returns_client_action_required_for_native_desktop(tmp_path):
    event_broker = RealtimeEventBroker()
    broker = AttentionNotificationBroker()
    item = broker.submit(inbox_item(NotificationLevel.URGENT))
    service = NotificationDeliveryService(broker)
    auth = CommandCenterAuth(lambda token: "actor:test" if token == "good" else None)
    client = TestClient(
        create_command_center_app(
            snapshot_provider=snapshot,
            event_broker=event_broker,
            inbox=broker,
            notification_service=service,
            auth=auth,
        )
    )
    response = client.post(
        f"/api/v1/command-center/inbox/{item.inbox_id}/dispatch?local_hour=12",
        headers={"Authorization": "Bearer good"},
    )
    assert response.status_code == 200
    deliveries = {x["channel"]: x for x in response.json()["deliveries"]}
    assert deliveries["operator_inbox"]["state"] == "DELIVERED"
    assert deliveries["windows_notification"]["state"] == "CLIENT_ACTION_REQUIRED"
    assert deliveries["windows_notification"]["action_link"].startswith("/command-center?inbox=")
