from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.qualification import QualificationStore, _pid_alive

ROOT = Path(__file__).resolve().parents[1]


class AdvanceableClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now = self._now + timedelta(**kwargs)


def _attest_four_hour(store: QualificationStore, tmp_path: Path) -> dict:
    run = store.start("UNATTENDED_4_HOUR", state_path=tmp_path / "state-4h")
    store._db.execute(
        """
        UPDATE qualification_runs
        SET status = 'ATTESTED', window_broken = 0, attested_elapsed_seconds = ?
        WHERE run_id = ?
        """,
        (4 * 3600, run["run_id"]),
    )
    store._db.execute("DELETE FROM qualification_locks WHERE lock_name = 'active-qualification'")
    store._db.commit()
    return store.get(run["run_id"])


def test_qualification_rejects_simulated_completion_and_72h_before_24h(tmp_path: Path):
    clock = AdvanceableClock()
    store = QualificationStore(tmp_path / "qualify.sqlite3", clock=clock, repository_root=ROOT)
    recovery = store.start("RECOVERY", state_path=tmp_path / "state")
    assert recovery["status"] == "RUNNING"
    store.heartbeat(recovery["run_id"])
    completed = store.complete(recovery["run_id"])
    assert completed["status"] == "ATTESTED"

    four = store.start("UNATTENDED_4_HOUR", state_path=tmp_path / "state")
    with pytest.raises(ValueError, match="cannot be simulated"):
        store.complete(four["run_id"])
    with pytest.raises(ValueError, match="4-hour"):
        store.start("UNATTENDED_24_HOUR", state_path=tmp_path / "state")
    clock.advance(hours=5)
    store.heartbeat(four["run_id"])
    with pytest.raises(ValueError, match="cannot be simulated"):
        store.complete(four["run_id"])
    store._db.execute(
        """
        UPDATE qualification_runs
        SET status = 'ATTESTED', window_broken = 0, attested_elapsed_seconds = ?
        WHERE run_id = ?
        """,
        (4 * 3600, four["run_id"]),
    )
    store._db.execute("DELETE FROM qualification_locks WHERE lock_name = 'active-qualification'")
    store._db.commit()

    day = store.start("UNATTENDED_24_HOUR", state_path=tmp_path / "state")
    with pytest.raises(ValueError, match="cannot be simulated"):
        store.complete(day["run_id"])
    with pytest.raises(ValueError, match="24-hour"):
        store.start("UNATTENDED_72_HOUR", state_path=tmp_path / "state")
    clock.advance(hours=25)
    store.heartbeat(day["run_id"])
    with pytest.raises(ValueError, match="cannot be simulated"):
        store.complete(day["run_id"])
    store.close()


def test_qualification_resumes_after_failure_and_reports_health(tmp_path: Path):
    clock = AdvanceableClock()
    store = QualificationStore(tmp_path / "qualify.sqlite3", clock=clock, repository_root=ROOT)
    run = store.start("RECOVERY", state_path=tmp_path / "state", process_id=4242)
    failed = store.fail(run["run_id"], reason="host-restart")
    assert failed["status"] == "FAILED"
    resumed = store.resume(run["run_id"], process_id=4343)
    assert resumed["status"] == "RESUMED"
    assert resumed["process_id"] == 4343
    health = store.health(run["run_id"])
    assert health["simulated_elapsed"] is False
    assert health["lease_id"].startswith("QLEASE-")
    assert health["fence"].startswith("QFENCE-")
    assert "resume" in " ".join(health["resume_command"])
    store.close()


def test_reconstructed_store_preserves_checkpoint(tmp_path: Path):
    clock = AdvanceableClock()
    path = tmp_path / "qualify.sqlite3"
    store = QualificationStore(path, clock=clock, repository_root=ROOT)
    run = store.start("RECOVERY", state_path=tmp_path / "state")
    run_id = run["run_id"]
    store.heartbeat(run_id)
    store.close()
    restored = QualificationStore(path, clock=clock, repository_root=ROOT)
    loaded = restored.get(run_id)
    assert loaded["run_id"] == run_id
    assert loaded["status"] == "RUNNING"
    restored.resume(run_id)
    assert restored.get(run_id)["status"] == "RESUMED"
    restored.close()


def test_pid_alive_does_not_signal_the_current_process():
    assert _pid_alive(os.getpid()) is True
    assert _pid_alive(0) is False
    assert _pid_alive(-1) is False


def test_concurrent_runner_is_rejected_without_interrupting_pytest(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    first = store.start("RECOVERY", state_path=tmp_path / "state")
    assert first["status"] == "RUNNING"
    with pytest.raises(ValueError, match="concurrent qualification runner"):
        store.start("RECOVERY", state_path=tmp_path / "state")
    store.close()


def test_recovery_drill_attests_controlled_process_loss(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    attested = store.recovery_drill(state_path=tmp_path / "state")
    assert attested["stage"] == "RECOVERY"
    assert attested["status"] == "ATTESTED"
    events = store._db.execute(
        "SELECT action FROM qualification_events WHERE run_id = ? ORDER BY created_at_utc",
        (attested["run_id"],),
    ).fetchall()
    actions = [str(row["action"]) for row in events]
    assert "START" in actions
    assert any(action.startswith("FAIL:") for action in actions)
    assert "RESUME" in actions
    assert "ATTEST" in actions
    store.close()


def test_24h_resume_breaks_uninterrupted_window(tmp_path: Path):
    store = QualificationStore(
        tmp_path / "qualify.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.2,
    )
    _attest_four_hour(store, tmp_path)
    run = store.start("UNATTENDED_24_HOUR", state_path=tmp_path / "state")
    store.fail(run["run_id"], reason="process-loss")
    resumed = store.resume(run["run_id"])
    assert resumed["window_broken"] == 1
    with pytest.raises(ValueError, match="uninterrupted window"):
        store.complete(run["run_id"])
    store.close()


def test_heartbeat_gap_disqualifies_unattended_window(tmp_path: Path):
    store = QualificationStore(
        tmp_path / "qualify.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=1.0,
    )
    _attest_four_hour(store, tmp_path)
    run = store.start("UNATTENDED_24_HOUR", state_path=tmp_path / "state")
    store._db.execute(
        "UPDATE qualification_runs SET last_heartbeat_utc = ? WHERE run_id = ?",
        ((datetime.now(UTC) - timedelta(seconds=10)).isoformat(), run["run_id"]),
    )
    store._db.commit()
    with pytest.raises(ValueError, match="heartbeat gap"):
        store.heartbeat(run["run_id"])
    assert store.get(run["run_id"])["status"] == "DISQUALIFIED"
    store.close()


def test_clock_rollback_and_fence_mismatch_disqualify(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    _attest_four_hour(store, tmp_path)
    run = store.start("UNATTENDED_24_HOUR", state_path=tmp_path / "state")
    store._db.execute(
        "UPDATE qualification_runs SET last_heartbeat_utc = ? WHERE run_id = ?",
        ((datetime.now(UTC) + timedelta(hours=2)).isoformat(), run["run_id"]),
    )
    store._db.commit()
    with pytest.raises(ValueError, match="clock rollback"):
        store.heartbeat(run["run_id"])
    store.close()

    store = QualificationStore(tmp_path / "qualify2.sqlite3", repository_root=ROOT)
    _attest_four_hour(store, tmp_path)
    run = store.start("UNATTENDED_24_HOUR", state_path=tmp_path / "state")
    with pytest.raises(ValueError, match="fence mismatch"):
        store.heartbeat(run["run_id"], fence="QFENCE-forged")
    assert store.get(run["run_id"])["status"] == "DISQUALIFIED"
    store.close()


def test_event_chain_edit_is_detected(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    _attest_four_hour(store, tmp_path)
    run = store.start("UNATTENDED_24_HOUR", state_path=tmp_path / "state")
    store._db.execute(
        "UPDATE qualification_runs SET last_event_sha256 = 'tampered' WHERE run_id = ?",
        (run["run_id"],),
    )
    store._db.commit()
    with pytest.raises(ValueError, match="event chain"):
        store.heartbeat(run["run_id"])
    store.close()


def test_event_chain_uses_insertion_order_when_timestamps_tie(tmp_path: Path):
    clock = AdvanceableClock()
    store = QualificationStore(tmp_path / "qualify.sqlite3", clock=clock, repository_root=ROOT)
    run = store.start("RECOVERY", state_path=tmp_path / "state")

    store.heartbeat(run["run_id"])
    repeated = store.heartbeat(run["run_id"])

    assert repeated["status"] == "RUNNING"
    store.close()


def test_concurrent_runner_is_rejected(tmp_path: Path):
    first = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    second = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    first.start("RECOVERY", state_path=tmp_path / "state")
    with pytest.raises(ValueError, match="concurrent"):
        second.start("RECOVERY", state_path=tmp_path / "other")
    first.close()
    second.close()


def test_stale_lock_from_dead_process_is_reclaimed(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    store._db.execute(
        """
        INSERT INTO qualification_locks (lock_name, run_id, process_id, fence, acquired_at_utc)
        VALUES ('active-qualification', 'QRUN-stale', 2147000000, 'QFENCE-stale', ?)
        """,
        (datetime.now(UTC).isoformat(),),
    )
    store._db.commit()
    started = store.start("RECOVERY", state_path=tmp_path / "state")
    assert started["status"] == "RUNNING"
    store.close()


def test_schema_comes_from_catalog_not_ad_hoc_create(tmp_path: Path):
    path = tmp_path / "qualify.sqlite3"
    store = QualificationStore(path, repository_root=ROOT)
    applied = {
        str(row[0])
        for row in store._db.execute("SELECT migration_id FROM schema_migrations").fetchall()
    }
    assert "PPDB-0021" in applied
    tables = {
        str(row[0])
        for row in store._db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"qualification_runs", "qualification_events", "qualification_locks"} <= tables
    store.close()
    source = (ROOT / "src/project_pipeline/autonomy_runtime/qualification.py").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS qualification_runs" not in source


def test_run_loop_and_orchestration_receipts(tmp_path: Path):
    store = QualificationStore(
        tmp_path / "qualify.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.01,
    )
    run = store.start("RECOVERY", state_path=tmp_path / "state")
    looped = store.run_loop(run["run_id"], cycles=2)
    assert looped["status"] == "RUNNING"
    stop_file = tmp_path / "stop.flag"
    stop_file.write_text("stop", encoding="utf-8")
    stopped = store.run_loop(run["run_id"], cycles=4, stop_path=stop_file)
    assert stopped["status"] == "STOPPED"
    store.close()

    store = QualificationStore(tmp_path / "orch.sqlite3", repository_root=ROOT)
    run = store.start("RECOVERY", state_path=tmp_path / "state")
    orch = store.orchestrate(
        run["run_id"],
        [[sys.executable, str(ROOT / "scripts" / "campaign_probe.py")]],
    )
    assert orch["orchestration_receipts"][0]["executed"] is True
    assert orch["orchestration_receipts"][0]["exit_code"] == 0
    assert orch["orchestration_receipts"][0]["command_sha256"]
    store.close()


def test_cli_recovery_status_and_stop(tmp_path: Path):
    database = tmp_path / "qualify.sqlite3"
    state = tmp_path / "state"
    state.mkdir()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    started = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_autonomy_qualification.py"),
            "start",
            "--database",
            str(database),
            "--state-path",
            str(state),
            "--stage",
            "RECOVERY",
            "--repository-root",
            str(ROOT),
            "--heartbeat-seconds",
            "0.05",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    payload = json.loads(started.stdout)
    run_id = payload["run_id"]
    health = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_autonomy_qualification.py"),
            "health",
            "--database",
            str(database),
            "--run-id",
            run_id,
            "--repository-root",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    assert json.loads(health.stdout)["run_id"] == run_id
    stopped = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_autonomy_qualification.py"),
            "stop",
            "--database",
            str(database),
            "--run-id",
            run_id,
            "--repository-root",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    assert json.loads(stopped.stdout)["status"] == "STOPPED"


def test_complete_is_idempotent_for_recovery(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    run = store.start("RECOVERY", state_path=tmp_path / "state")
    first = store.complete(run["run_id"])
    second = store.complete(run["run_id"])
    assert first["status"] == second["status"] == "ATTESTED"
    store.close()
