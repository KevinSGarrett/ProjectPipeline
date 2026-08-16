from __future__ import annotations

import sqlite3
from pathlib import Path

from project_pipeline.command_center.models import (
    DirectorChatMessage,
    InboxItem,
    IncidentCase,
    NotificationDecision,
    NotificationDeliveryAttempt,
)
from project_pipeline.contracts import EventEnvelope
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class CommandCenterStore:
    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> CommandCenterStore:
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.initialize()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.connection is not None:
            self.connection.close()
        self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("command center store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def save_event(self, event: EventEnvelope) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO command_center_events(event_id,project_id,sequence,event_type,occurred_at_utc,payload_json) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(event_id) DO UPDATE SET sequence=excluded.sequence,payload_json=excluded.payload_json",
                (
                    event.event_id,
                    event.project_id,
                    event.sequence,
                    event.event_type,
                    event.occurred_at_utc.isoformat(),
                    event.model_dump_json(),
                ),
            )

    def save_inbox(self, item: InboxItem) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO command_center_inbox(inbox_id,project_id,dedupe_key,level,state,priority_score,created_at_utc,payload_json) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(inbox_id) DO UPDATE SET level=excluded.level,state=excluded.state,priority_score=excluded.priority_score,payload_json=excluded.payload_json",
                (
                    item.inbox_id,
                    item.project_id,
                    item.dedupe_key,
                    int(item.level),
                    item.state.value,
                    item.priority_score,
                    item.created_at_utc.isoformat(),
                    item.model_dump_json(),
                ),
            )

    def save_notification(self, item: NotificationDecision) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO command_center_notifications(notification_id,inbox_id,level,suppressed,decided_at_utc,payload_json) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(notification_id) DO UPDATE SET payload_json=excluded.payload_json",
                (
                    item.notification_id,
                    item.inbox_id,
                    int(item.level),
                    int(item.suppressed),
                    item.decided_at_utc.isoformat(),
                    item.model_dump_json(),
                ),
            )

    def save_director_message(self, item: DirectorChatMessage) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO command_center_director_messages(message_id,conversation_id,project_id,role,scope,created_at_utc,payload_json) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(message_id) DO UPDATE SET payload_json=excluded.payload_json",
                (
                    item.message_id,
                    item.conversation_id,
                    item.project_id,
                    item.role.value,
                    item.scope.value,
                    item.created_at_utc.isoformat(),
                    item.model_dump_json(),
                ),
            )

    def save_incident_case(self, item: IncidentCase) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO command_center_incident_cases(incident_id,project_id,state,severity,updated_at_utc,payload_json) VALUES(?,?,?,?,CURRENT_TIMESTAMP,?) "
                "ON CONFLICT(incident_id) DO UPDATE SET state=excluded.state,severity=excluded.severity,updated_at_utc=CURRENT_TIMESTAMP,payload_json=excluded.payload_json",
                (
                    item.incident.incident_id,
                    item.project_id,
                    item.state.value,
                    int(item.severity),
                    item.model_dump_json(),
                ),
            )

    def save_delivery(self, item: NotificationDeliveryAttempt) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO command_center_notification_deliveries(delivery_id,notification_id,inbox_id,channel,adapter_id,state,attempt_number,created_at_utc,payload_json) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(delivery_id) DO UPDATE SET state=excluded.state,attempt_number=excluded.attempt_number,payload_json=excluded.payload_json",
                (
                    item.delivery_id,
                    item.notification_id,
                    item.inbox_id,
                    item.channel,
                    item.adapter_id,
                    item.state.value,
                    item.attempt_number,
                    item.created_at_utc.isoformat(),
                    item.model_dump_json(),
                ),
            )

    def record_control_request(
        self, request_id: str, command_id: str, actor_id: str, status: str, payload_json: str
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO command_center_control_requests(request_id,command_id,actor_id,status,created_at_utc,payload_json) VALUES(?,?,?,?,CURRENT_TIMESTAMP,?)",
                (request_id, command_id, actor_id, status, payload_json),
            )

    def status(self) -> dict[str, int]:
        tables = (
            "command_center_events",
            "command_center_inbox",
            "command_center_notifications",
            "command_center_control_requests",
            "command_center_director_messages",
            "command_center_incident_cases",
            "command_center_notification_deliveries",
        )
        return {
            table: int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
