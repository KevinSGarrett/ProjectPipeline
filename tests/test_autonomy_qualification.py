from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.qualification import QualificationStore


class AdvanceableClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now = self._now + timedelta(**kwargs)


def test_qualification_rejects_simulated_completion_and_72h_before_24h(tmp_path: Path):
    clock = AdvanceableClock()
    store = QualificationStore(tmp_path / "qualify.sqlite3", clock=clock)
    recovery = store.start("RECOVERY", state_path=tmp_path / "state")
    assert recovery["status"] == "RUNNING"
    store.heartbeat(recovery["run_id"])
    completed = store.complete(recovery["run_id"])
    assert completed["status"] == "ATTESTED"

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
    store = QualificationStore(tmp_path / "qualify.sqlite3", clock=clock)
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
    store = QualificationStore(path, clock=clock)
    run = store.start("RECOVERY", state_path=tmp_path / "state")
    run_id = run["run_id"]
    store.heartbeat(run_id)
    store.close()
    restored = QualificationStore(path, clock=clock)
    loaded = restored.get(run_id)
    assert loaded["run_id"] == run_id
    assert loaded["status"] == "RUNNING"
    restored.resume(run_id)
    assert restored.get(run_id)["status"] == "RESUMED"
    restored.close()
