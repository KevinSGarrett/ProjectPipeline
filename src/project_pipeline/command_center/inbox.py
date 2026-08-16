from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from project_pipeline.command_center.models import (
    InboxItem,
    InboxState,
    NotificationDecision,
    NotificationLevel,
    NotificationPolicy,
)


class AttentionNotificationBroker:
    def __init__(self, policy: NotificationPolicy | None = None) -> None:
        self.policy = policy or NotificationPolicy()
        self._items: dict[str, InboxItem] = {}
        self._dedupe: dict[str, str] = {}

    @staticmethod
    def priority(item: InboxItem) -> int:
        score = int(item.level) * 100
        score += 50 if item.critical_path else 0
        score += min(item.blocked_tasks * 10, 100)
        score += min(item.duration_minutes // 15, 40)
        score -= 30 if item.operator_already_aware else 0
        score -= 15 if item.recoverable_automatically else 0
        return max(score, 0)

    def submit(self, item: InboxItem) -> InboxItem:
        adjusted = item.model_copy(update={"priority_score": self.priority(item)})
        previous_id = self._dedupe.get(item.dedupe_key)
        if previous_id and previous_id in self._items:
            previous = self._items[previous_id]
            if previous.state is not InboxState.RESOLVED:
                adjusted = adjusted.model_copy(
                    update={
                        "inbox_id": previous.inbox_id,
                        "created_at_utc": previous.created_at_utc,
                    }
                )
        self._items[adjusted.inbox_id] = adjusted
        self._dedupe[adjusted.dedupe_key] = adjusted.inbox_id
        return adjusted

    def list_open(self) -> tuple[InboxItem, ...]:
        rows = [x for x in self._items.values() if x.state is not InboxState.RESOLVED]
        return tuple(sorted(rows, key=lambda x: (-x.priority_score, x.created_at_utc, x.inbox_id)))

    def acknowledge(self, inbox_id: str, *, now: datetime | None = None) -> InboxItem:
        item = self._items[inbox_id]
        updated = item.model_copy(
            update={
                "state": InboxState.ACKNOWLEDGED,
                "acknowledged_at_utc": now or datetime.now(UTC),
            }
        )
        self._items[inbox_id] = updated
        return updated

    def resolve(self, inbox_id: str, *, now: datetime | None = None) -> InboxItem:
        item = self._items[inbox_id]
        updated = item.model_copy(
            update={
                "state": InboxState.RESOLVED,
                "resolved_at_utc": now or datetime.now(UTC),
            }
        )
        self._items[inbox_id] = updated
        return updated

    def route(self, item: InboxItem, *, local_hour: int) -> NotificationDecision:
        quiet = self._is_quiet(local_hour)
        channels: list[str] = []
        suppressed = False
        reason = None
        if item.level is NotificationLevel.INFORMATIONAL:
            channels = ["timeline"]
        elif item.level is NotificationLevel.NOTICE:
            channels = ["command_center_badge"]
        elif item.level is NotificationLevel.ATTENTION:
            channels = ["operator_inbox"]
            if self.policy.windows_notifications_enabled and not quiet:
                channels.append("windows_notification")
        elif item.level is NotificationLevel.URGENT:
            channels = (
                ["operator_inbox", "windows_notification"]
                if self.policy.windows_notifications_enabled
                else ["operator_inbox"]
            )
            if self.policy.remote_channels_enabled:
                channels.append("remote")
        else:
            channels = ["operator_inbox", "persistent_desktop"]
            if self.policy.remote_channels_enabled:
                channels.append("remote")
        if quiet and item.level in {NotificationLevel.NOTICE, NotificationLevel.ATTENTION}:
            suppressed = True
            reason = "quiet_hours_nonurgent"
            channels = [x for x in channels if x not in {"windows_notification", "remote"}]
        return NotificationDecision(
            notification_id=f"notify:{uuid4()}",
            inbox_id=item.inbox_id,
            level=item.level,
            channels=tuple(channels),
            suppressed=suppressed,
            suppression_reason=reason,
            escalation_required=item.level >= NotificationLevel.URGENT,
        )

    def _is_quiet(self, hour: int) -> bool:
        if not 0 <= hour <= 23:
            raise ValueError("local_hour must be 0..23")
        start, end = self.policy.quiet_hours_start, self.policy.quiet_hours_end
        return (start <= hour or hour < end) if start > end else start <= hour < end
