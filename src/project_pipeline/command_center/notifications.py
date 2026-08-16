from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib import request as urllib_request
from uuid import uuid4

from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import (
    InboxItem,
    NotificationDeliveryAttempt,
    NotificationDeliveryState,
    NotificationDispatchResult,
    NotificationPolicy,
)


class NotificationAdapter(Protocol):
    adapter_id: str
    remote: bool

    def deliver(self, item: InboxItem, *, action_link: str | None = None) -> bool: ...


class AppriseNotificationAdapter:
    adapter_id = "apprise"
    remote = True

    def __init__(self, urls: tuple[str, ...]) -> None:
        self.urls = urls

    def deliver(self, item: InboxItem, *, action_link: str | None = None) -> bool:
        try:
            import apprise
        except ImportError as exc:
            raise RuntimeError("apprise optional dependency is unavailable") from exc
        client = apprise.Apprise()
        for url in self.urls:
            client.add(url)
        body = (
            f"{item.impact}\nAction: {item.exact_action}\nVerify: {item.post_action_verification}"
        )
        if action_link:
            body += f"\nOpen: {action_link}"
        return bool(client.notify(title=item.title, body=body))


class NtfyHttpNotificationAdapter:
    adapter_id = "ntfy-http"
    remote = True

    def __init__(
        self,
        endpoint: str,
        topic: str,
        *,
        transport: Callable[[str, bytes, dict[str, str]], int] | None = None,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("ntfy endpoint must be HTTP(S)")
        if not topic or "/" in topic:
            raise ValueError("ntfy topic must be a non-empty single segment")
        self.endpoint = endpoint.rstrip("/")
        self.topic = topic
        self.transport = transport or self._urllib_transport

    def deliver(self, item: InboxItem, *, action_link: str | None = None) -> bool:
        payload = {
            "topic": self.topic,
            "title": item.title,
            "message": f"{item.impact}\nAction: {item.exact_action}\nVerify: {item.post_action_verification}",
            "priority": 5 if int(item.level) >= 4 else 4 if int(item.level) >= 3 else 3,
            "tags": ["warning" if int(item.level) >= 3 else "information_source"],
        }
        if action_link:
            payload["click"] = action_link
        status = self.transport(
            self.endpoint,
            json.dumps(payload).encode("utf-8"),
            {"Content-Type": "application/json", "Idempotency-Key": item.inbox_id},
        )
        return 200 <= int(status) < 300

    @staticmethod
    def _urllib_transport(url: str, body: bytes, headers: dict[str, str]) -> int:
        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        with urllib_request.urlopen(req, timeout=10) as response:
            return int(response.status)


class NotificationDeliveryService:
    """Delivery mechanics behind the authoritative Project Pipeline notification broker."""

    _desktop_channels = frozenset({"windows_notification", "persistent_desktop"})
    _internal_channels = frozenset({"timeline", "command_center_badge", "operator_inbox"})

    def __init__(
        self,
        broker: AttentionNotificationBroker,
        *,
        policy: NotificationPolicy | None = None,
        adapters: dict[str, NotificationAdapter] | None = None,
        remote_adapter_id: str = "apprise",
        delivery_sink: Callable[[NotificationDeliveryAttempt], None] | None = None,
        max_attempts: int = 3,
        retry_backoff_seconds: int = 60,
    ) -> None:
        self.broker = broker
        self.policy = policy or broker.policy
        self.adapters = adapters or {}
        self.remote_adapter_id = remote_adapter_id
        self.delivery_sink = delivery_sink
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self._successful: set[tuple[str, str]] = set()
        self._attempts: dict[tuple[str, str], int] = {}

    def dispatch(
        self,
        item: InboxItem,
        *,
        local_hour: int,
        action_link: str | None = None,
        now: datetime | None = None,
    ) -> NotificationDispatchResult:
        decision = self.broker.route(item, local_hour=local_hour)
        timestamp = now or datetime.now(UTC)
        deliveries = tuple(
            self._dispatch_channel(item, decision.notification_id, channel, action_link, timestamp)
            for channel in decision.channels
        )
        return NotificationDispatchResult(
            decision=decision,
            deliveries=deliveries,
            remote_delivery_enabled=self.policy.remote_channels_enabled,
        )

    def _dispatch_channel(
        self,
        item: InboxItem,
        notification_id: str,
        channel: str,
        action_link: str | None,
        now: datetime,
    ) -> NotificationDeliveryAttempt:
        key = (item.inbox_id, channel)
        if key in self._successful:
            return self._record(
                NotificationDeliveryAttempt(
                    delivery_id=f"delivery:{uuid4()}",
                    notification_id=notification_id,
                    inbox_id=item.inbox_id,
                    channel=channel,
                    adapter_id="dedupe",
                    state=NotificationDeliveryState.DUPLICATE_SUPPRESSED,
                    remote=channel == "remote",
                    action_link=action_link,
                )
            )
        if channel in self._internal_channels:
            attempt = NotificationDeliveryAttempt(
                delivery_id=f"delivery:{uuid4()}",
                notification_id=notification_id,
                inbox_id=item.inbox_id,
                channel=channel,
                adapter_id="project-pipeline-internal",
                state=NotificationDeliveryState.DELIVERED,
                delivered_at_utc=now,
                action_link=action_link,
            )
            self._successful.add(key)
            return self._record(attempt)
        if channel in self._desktop_channels:
            return self._record(
                NotificationDeliveryAttempt(
                    delivery_id=f"delivery:{uuid4()}",
                    notification_id=notification_id,
                    inbox_id=item.inbox_id,
                    channel=channel,
                    adapter_id="tauri-client",
                    state=NotificationDeliveryState.CLIENT_ACTION_REQUIRED,
                    action_link=action_link,
                )
            )
        if channel == "remote":
            return self._deliver_remote(item, notification_id, action_link, now)
        return self._record(
            NotificationDeliveryAttempt(
                delivery_id=f"delivery:{uuid4()}",
                notification_id=notification_id,
                inbox_id=item.inbox_id,
                channel=channel,
                adapter_id="none",
                state=NotificationDeliveryState.SUPPRESSED,
                error_category="unsupported_channel",
                action_link=action_link,
            )
        )

    def _deliver_remote(
        self,
        item: InboxItem,
        notification_id: str,
        action_link: str | None,
        now: datetime,
    ) -> NotificationDeliveryAttempt:
        key = (item.inbox_id, "remote")
        if not self.policy.remote_channels_enabled:
            return self._record(
                NotificationDeliveryAttempt(
                    delivery_id=f"delivery:{uuid4()}",
                    notification_id=notification_id,
                    inbox_id=item.inbox_id,
                    channel="remote",
                    adapter_id=self.remote_adapter_id,
                    state=NotificationDeliveryState.SUPPRESSED,
                    remote=True,
                    action_link=action_link,
                    error_category="remote_delivery_disabled_by_policy",
                )
            )
        adapter = self.adapters.get(self.remote_adapter_id)
        if adapter is None:
            return self._record(
                NotificationDeliveryAttempt(
                    delivery_id=f"delivery:{uuid4()}",
                    notification_id=notification_id,
                    inbox_id=item.inbox_id,
                    channel="remote",
                    adapter_id=self.remote_adapter_id,
                    state=NotificationDeliveryState.FAILED,
                    remote=True,
                    action_link=action_link,
                    error_category="remote_adapter_unavailable",
                )
            )
        count = self._attempts.get(key, 0) + 1
        self._attempts[key] = count
        try:
            delivered = bool(adapter.deliver(item, action_link=action_link))
            error_category = None if delivered else "adapter_reported_failure"
        except Exception as exc:
            delivered = False
            error_category = type(exc).__name__
        if delivered:
            self._successful.add(key)
            return self._record(
                NotificationDeliveryAttempt(
                    delivery_id=f"delivery:{uuid4()}",
                    notification_id=notification_id,
                    inbox_id=item.inbox_id,
                    channel="remote",
                    adapter_id=adapter.adapter_id,
                    state=NotificationDeliveryState.DELIVERED,
                    attempt_number=count,
                    remote=True,
                    action_link=action_link,
                    delivered_at_utc=now,
                )
            )
        retry = count < self.max_attempts
        return self._record(
            NotificationDeliveryAttempt(
                delivery_id=f"delivery:{uuid4()}",
                notification_id=notification_id,
                inbox_id=item.inbox_id,
                channel="remote",
                adapter_id=adapter.adapter_id,
                state=NotificationDeliveryState.RETRY_SCHEDULED
                if retry
                else NotificationDeliveryState.FAILED,
                attempt_number=count,
                remote=True,
                action_link=action_link,
                error_category=error_category,
                next_retry_at_utc=now + timedelta(seconds=self.retry_backoff_seconds * count)
                if retry
                else None,
            )
        )

    def _record(self, attempt: NotificationDeliveryAttempt) -> NotificationDeliveryAttempt:
        if self.delivery_sink is not None:
            self.delivery_sink(attempt)
        return attempt
