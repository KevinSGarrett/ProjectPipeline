from __future__ import annotations

from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.incidents import IncidentManager
from project_pipeline.command_center.models import InboxItem, NotificationLevel, NotificationPolicy
from project_pipeline.command_center.notifications import NotificationDeliveryService
from project_pipeline.command_center.realtime import RealtimeEventBroker
from project_pipeline.contracts import EventEnvelope
from project_pipeline.domain.resilience import FailureDomain, HumanRequiredIncident


def _event(n: int) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"event:sim:{n}",
        event_type="simulation.tick",
        project_id="PROJ-SIM",
        producer="command-center-simulation",
        correlation_id="corr:sim",
        aggregate_type="simulation",
        aggregate_id="sim:1",
        payload={"n": n},
    )


def run_command_center_simulations() -> dict[str, bool]:
    broker = RealtimeEventBroker(retention=10)
    a = broker.publish(_event(1))
    b = broker.publish(_event(2))
    c = broker.publish(_event(3))
    replay = broker.page(after_sequence=a.sequence)
    reconnect_ok = [x.sequence for x in replay.events] == [b.sequence, c.sequence]
    attention = AttentionNotificationBroker()
    base = InboxItem(
        inbox_id="inbox:sim:1",
        project_id="PROJ-SIM",
        dedupe_key="same",
        kind="incident",
        level=NotificationLevel.ATTENTION,
        title="Need operator",
        impact="work blocked",
        exact_action="inspect incident",
        post_action_verification="rerun verification",
        blocked_tasks=2,
    )
    first = attention.submit(base)
    second = attention.submit(
        base.model_copy(update={"inbox_id": "inbox:sim:2", "duration_minutes": 30})
    )
    dedupe_ok = first.inbox_id == second.inbox_id and len(attention.list_open()) == 1
    quiet = attention.route(second, local_hour=23)
    quiet_ok = quiet.suppressed and "windows_notification" not in quiet.channels
    incident_manager = IncidentManager(attention)
    incident = HumanRequiredIncident(
        incident_id="INCIDENT-BBBBBBBBBBBBBBBBBBBB",
        failure_domain=FailureDomain.API,
        summary="simulation repair required",
        exact_human_action="repair the simulated dependency",
        blocked_work=("work:blocked",),
        unaffected_work=("work:safe",),
        verification_steps=("dependency healthy",),
        stale_assumptions_to_invalidate=("dependency failed",),
    )
    case = incident_manager.open(incident, project_id="PROJ-SIM")
    incident_manager.begin_recovery(case.incident.incident_id)
    failed = incident_manager.verify(
        case.incident.incident_id,
        verification_results={"dependency": False},
        stale_assumptions_invalidated=True,
        reconciliation_complete=True,
    )
    repair_gate_ok = failed.state.value == "RECOVERING"
    notification = NotificationDeliveryService(
        attention, policy=NotificationPolicy(remote_channels_enabled=False)
    ).dispatch(attention.list_open()[0], local_hour=12)
    remote_default_off_ok = (
        not notification.remote_delivery_enabled and "remote" not in notification.decision.channels
    )
    return {
        "reconnect_replay": reconnect_ok,
        "notification_dedupe": dedupe_ok,
        "quiet_hours": quiet_ok,
        "incident_repair_gate": repair_gate_ok,
        "remote_default_off": remote_default_off_ok,
    }
