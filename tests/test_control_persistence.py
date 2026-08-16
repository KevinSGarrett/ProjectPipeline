from __future__ import annotations

import sqlite3
from pathlib import Path

from project_pipeline.control import ControlStore, ProjectControlKernel
from project_pipeline.persistence import SQLiteMigrationRunner, SQLiteStateStore
from project_pipeline.services import CoreStateService

ROOT = Path(__file__).resolve().parents[1]


def test_control_migration_applies_and_rolls_back(tmp_path: Path) -> None:
    db = sqlite3.connect(tmp_path / "migrations.db")
    runner = SQLiteMigrationRunner(db, ROOT)
    status = runner.apply_all()
    assert "PPDB-0006" in status.applied
    while runner.status().latest_applied != "PPDB-0006":
        runner.rollback_last()
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0005"
    with __import__("pytest").raises(sqlite3.OperationalError):
        db.execute("SELECT COUNT(*) FROM control_snapshots").fetchone()
    db.close()


def test_control_snapshot_roundtrip_and_projection_rows(tmp_path: Path) -> None:
    path = tmp_path / "control.db"
    with SQLiteStateStore(path, ROOT) as state_store:
        CoreStateService(state_store, ROOT).initialize_from_repository()
        snapshot = ProjectControlKernel(ROOT, state_store, "PROJECT-PIPELINE").evaluate()
    with ControlStore(path, ROOT) as store:
        store.save_snapshot(snapshot)
        loaded = store.get_snapshot(snapshot.snapshot_id)
        assert loaded == snapshot
        assert store.latest_snapshot("PROJECT-PIPELINE") == snapshot
        status = store.status("PROJECT-PIPELINE")
        assert status["snapshot_count"] == 1
        assert status["ready_count"] == snapshot.sequence.ready_count
        count = store.db.execute(
            "SELECT COUNT(*) FROM control_sequence_items WHERE snapshot_id=?",
            (snapshot.snapshot_id,),
        ).fetchone()[0]
        assert count == len(snapshot.sequence.ordered_ready_work)


def test_saving_same_snapshot_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "control.db"
    with SQLiteStateStore(path, ROOT) as state_store:
        CoreStateService(state_store, ROOT).initialize_from_repository()
        snapshot = ProjectControlKernel(ROOT, state_store, "PROJECT-PIPELINE").evaluate()
    with ControlStore(path, ROOT) as store:
        store.save_snapshot(snapshot)
        store.save_snapshot(snapshot)
        assert store.status("PROJECT-PIPELINE")["snapshot_count"] == 1
