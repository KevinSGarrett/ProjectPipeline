from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import (
    InboxItem,
    InboxState,
    NotificationLevel,
    NotificationPolicy,
)


def item(**updates):
    base = dict(
        inbox_id="inbox:test:1",
        project_id="PROJ-TEST",
        dedupe_key="incident:1",
        kind="incident",
        level=NotificationLevel.ATTENTION,
        title="Operator needed",
        impact="Critical task blocked",
        exact_action="Inspect and repair",
        post_action_verification="Run verification",
        critical_path=True,
        blocked_tasks=2,
        duration_minutes=30,
    )
    base.update(updates)
    return InboxItem(**base)


def test_priority_uses_impact_blockage_duration_and_recoverability():
    b = AttentionNotificationBroker()
    high = b.submit(item())
    low = b.submit(
        item(
            inbox_id="inbox:test:2",
            dedupe_key="incident:2",
            critical_path=False,
            blocked_tasks=0,
            duration_minutes=0,
            recoverable_automatically=True,
            operator_already_aware=True,
        )
    )
    assert high.priority_score > low.priority_score


def test_deduplication_keeps_stable_inbox_identity():
    b = AttentionNotificationBroker()
    first = b.submit(item())
    second = b.submit(item(inbox_id="inbox:test:new", duration_minutes=90))
    assert first.inbox_id == second.inbox_id
    assert len(b.list_open()) == 1


def test_acknowledge_and_resolve_are_explicit_states():
    b = AttentionNotificationBroker()
    x = b.submit(item())
    assert b.acknowledge(x.inbox_id).state is InboxState.ACKNOWLEDGED
    assert b.resolve(x.inbox_id).state is InboxState.RESOLVED
    assert b.list_open() == ()


def test_quiet_hours_suppress_nonurgent_desktop_notice():
    b = AttentionNotificationBroker(NotificationPolicy(quiet_hours_start=22, quiet_hours_end=7))
    x = b.submit(item())
    d = b.route(x, local_hour=23)
    assert d.suppressed and "windows_notification" not in d.channels


def test_critical_breaks_through_quiet_hours_and_can_use_remote():
    b = AttentionNotificationBroker(NotificationPolicy(remote_channels_enabled=True))
    x = b.submit(item(level=NotificationLevel.CRITICAL))
    d = b.route(x, local_hour=23)
    assert (
        not d.suppressed
        and "persistent_desktop" in d.channels
        and "remote" in d.channels
        and d.escalation_required
    )
