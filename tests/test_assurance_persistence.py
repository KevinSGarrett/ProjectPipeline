import sqlite3
from pathlib import Path

import pytest

from project_pipeline.assurance.persistence import AssuranceStore
from project_pipeline.assurance.simulation import simulate_scenario, supported_scenarios
from project_pipeline.domain.assurance import (
    TruthKind,
    TruthRecord,
    assurance_identifier,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner, load_migration_catalog


def test_ppdb_0012_is_reversible_without_damaging_ppdb_0011(tmp_path: Path):
    root = Path.cwd()
    conn = sqlite3.connect(tmp_path / "assurance.db")
    runner = SQLiteMigrationRunner(conn, root)
    status = runner.apply_all()
    assert status.latest_applied == "PPDB-0020"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assurance_gate_evaluations'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()
    after_runtime = runner.rollback_last()
    assert after_runtime.latest_applied == "PPDB-0019"
    after_audit = runner.rollback_last()
    assert after_audit.latest_applied == "PPDB-0018"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='lifecycle_portfolio_projects'"
    ).fetchone()
    after_lifecycle = runner.rollback_last()
    assert after_lifecycle.latest_applied == "PPDB-0017"
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='lifecycle_portfolio_projects'"
    ).fetchone()
    after_interaction_layer = runner.rollback_last()
    assert after_interaction_layer.latest_applied == "PPDB-0016"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='command_center_events'"
    ).fetchone()
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='command_center_director_messages'"
    ).fetchone()
    after_command_center = runner.rollback_last()
    assert after_command_center.latest_applied == "PPDB-0015"
    after_resilience = runner.rollback_last()
    assert after_resilience.latest_applied == "PPDB-0014"
    after_security = runner.rollback_last()
    assert after_security.latest_applied == "PPDB-0013"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assurance_gate_evaluations'"
    ).fetchone()
    after_verification = runner.rollback_last()
    assert after_verification.latest_applied == "PPDB-0012"
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assurance_gate_evaluations'"
    ).fetchone()
    after_assurance = runner.rollback_last()
    assert after_assurance.latest_applied == "PPDB-0011"
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assurance_gate_evaluations'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()
    conn.close()


def test_migration_catalog_declares_assurance_dependency():
    migration = next(
        item
        for item in load_migration_catalog(Path.cwd()).migrations
        if item.migration_id == "PPDB-0012"
    )
    assert migration.depends_on == ("PPDB-0011",)
    assert migration.name == "execution_assurance_completion_gate"


def test_assurance_store_is_immutable(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "store.db")
    SQLiteMigrationRunner(conn, Path.cwd()).apply_all()
    conn.close()
    store = AssuranceStore(tmp_path / "store.db")
    value = TruthRecord(
        truth_id=assurance_identifier("TRUTH", "subject", "claim"),
        subject_id="subject",
        kind=TruthKind.CLAIM,
        statement="claim one",
    )
    store.save_truth("PROJECT-PIPELINE", value)
    store.save_truth("PROJECT-PIPELINE", value)
    changed = value.model_copy(update={"statement": "different claim"})
    with pytest.raises(ValueError):
        store.save_truth("PROJECT-PIPELINE", changed)
    assert store.status("PROJECT-PIPELINE")["truth_records"] == 1


def test_all_assurance_simulations_pass():
    results = [simulate_scenario(name) for name in supported_scenarios()]
    assert len(results) == 4
    assert all(result.passed for result in results)
    assert {result.scenario for result in results} == set(supported_scenarios())
