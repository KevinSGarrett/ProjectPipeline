from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.autonomy_runtime.recheck import AutonomousRecheckStore
from project_pipeline.autonomy_runtime.supervisor import PersistentSupervisor
from project_pipeline.command_center.autonomy import project_autonomy_runtime


def test_recheck_is_durable_due_and_does_not_globally_stop(tmp_path: Path) -> None:
    store = AutonomousRecheckStore(tmp_path / "rechecks.json")
    now = datetime(2026, 8, 18, 20, 0, tzinfo=UTC)
    first = store.schedule(
        capability="cursor-cli",
        reason="cursor-cli executable unavailable after autonomous discovery",
        interval_seconds=900,
        now=now,
        affected_lane_ids=("cursor-cli",),
        continuing_lane_ids=("windows-service", "command-center"),
    )
    reloaded = AutonomousRecheckStore(tmp_path / "rechecks.json")
    assert reloaded.due(now=now) == ()
    due = reloaded.due(now=now + timedelta(seconds=901))
    assert len(due) == 1
    assert due[0]["capability"] == "cursor-cli"
    assert due[0]["status"] == "BLOCKED_EXTERNAL"
    assert first["owner"] == "autonomy-runtime"
    snapshot = reloaded.snapshot()
    assert snapshot["global_stop"] is False
    assert "command-center" in snapshot["items"][0]["continuing_lane_ids"]
    encoded = (tmp_path / "rechecks.json").read_text(encoding="utf-8")
    assert "HUMAN_REQUIRED" not in encoded
    assert "operator session" not in encoded


def test_command_center_projects_durable_recheck_without_human_assignment(
    tmp_path: Path,
) -> None:
    supervisor = PersistentSupervisor(tmp_path / "sup.db")
    supervisor.close()
    store = AutonomousRecheckStore(tmp_path / "rechecks.json")
    store.schedule(
        capability="cursor-cli",
        reason="cursor-cli executable unavailable",
        continuing_lane_ids=("lane-healthy",),
    )
    snapshot = project_autonomy_runtime(
        supervisor_state=tmp_path / "sup.db",
        recheck_state=tmp_path / "rechecks.json",
        ready_task_ids=["PP-TASK-000384"],
    )
    rechecks = snapshot["context_summary"]["autonomous_rechecks"]
    assert rechecks["count"] == 1
    assert rechecks["global_stop"] is False
    assert rechecks["items"][0]["capability"] == "cursor-cli"
    assert "HUMAN_REQUIRED" not in str(snapshot)
    assert "operator session" not in str(snapshot)
