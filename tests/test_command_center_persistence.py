from project_pipeline.command_center.inbox import AttentionNotificationBroker
from project_pipeline.command_center.models import InboxItem, NotificationLevel
from project_pipeline.command_center.persistence import CommandCenterStore
from project_pipeline.contracts import EventEnvelope
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


def test_command_center_migration_is_latest_and_reversible(tmp_path, project_root):
    with CommandCenterStore(tmp_path / "cc.db", project_root) as store:
        runner = SQLiteMigrationRunner(store.db, project_root)
        status = runner.status()
        assert status.latest_applied == "PPDB-0025"
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
        runner.rollback_last()
        assert runner.status().latest_applied == "PPDB-0019"
        runner.rollback_last()
        assert runner.status().latest_applied == "PPDB-0018"
        runner.rollback_last()
        assert runner.status().latest_applied == "PPDB-0017"
        runner.rollback_last()
        assert runner.status().latest_applied == "PPDB-0016"


def test_command_center_store_records_projection_artifacts(tmp_path, project_root):
    with CommandCenterStore(tmp_path / "cc.db", project_root) as store:
        e = EventEnvelope(
            event_id="event:persist:1",
            event_type="work.changed",
            project_id="PROJ-TEST",
            producer="test",
            correlation_id="corr:test",
            aggregate_type="task",
            aggregate_id="task:1",
            sequence=1,
        )
        store.save_event(e)
        b = AttentionNotificationBroker()
        i = b.submit(
            InboxItem(
                inbox_id="inbox:persist:1",
                project_id="PROJ-TEST",
                dedupe_key="d:1",
                kind="incident",
                level=NotificationLevel.ATTENTION,
                title="Need action",
                impact="blocked",
                exact_action="repair",
                post_action_verification="verify",
            )
        )
        store.save_inbox(i)
        store.save_notification(b.route(i, local_hour=12))
        store.record_control_request("request:1", "command:1", "actor:test", "REQUESTED", "{}")
        assert store.status() == {
            "command_center_events": 1,
            "command_center_inbox": 1,
            "command_center_notifications": 1,
            "command_center_control_requests": 1,
            "command_center_director_messages": 0,
            "command_center_incident_cases": 0,
            "command_center_notification_deliveries": 0,
        }
