import sqlite3
from pathlib import Path

from project_pipeline.persistence.migrations import SQLiteMigrationRunner, load_migration_catalog


def test_ppdb_0011_is_reversible_without_damaging_ppdb_0010(tmp_path: Path):
    root = Path.cwd()
    conn = sqlite3.connect(tmp_path / "migrations.db")
    runner = SQLiteMigrationRunner(conn, root)
    status = runner.apply_all()
    assert status.latest_applied == "PPDB-0021"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assurance_gate_evaluations'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()

    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0020"
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0019"

    # Rolling back Pass 25 audit immutability must preserve lifecycle state.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0018"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='lifecycle_portfolio_projects'"
    ).fetchone()

    # Rolling back Pass 22 lifecycle state must preserve Pass 21 and lower layers.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0017"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='command_center_director_messages'"
    ).fetchone()
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='lifecycle_portfolio_projects'"
    ).fetchone()

    # Rolling back Pass 21 interaction/delivery state must preserve Command Center and lower layers.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0016"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='command_center_events'"
    ).fetchone()
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='command_center_director_messages'"
    ).fetchone()

    # Rolling back Command Center must not damage Resilience, Security, Verification, Assurance, or Budget state.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0015"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()

    # Rolling back Resilience must not damage Security, Verification, Assurance, or Budget state.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0014"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()

    # Rolling back Security must not damage Verification, Assurance, or Budget state.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0013"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()

    # Rolling back Verification must not damage Assurance or Budget state.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0012"
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_runs'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assurance_gate_evaluations'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()

    # Rolling back Assurance must not damage the Budget schema.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0011"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assurance_gate_evaluations'"
    ).fetchone()

    # Rolling back PPDB-0011 removes only Budget Governor state.
    rolled = runner.rollback_last()
    assert rolled.latest_applied == "PPDB-0010"
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_ledger'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='orchestration_workflows'"
    ).fetchone()
    conn.close()


def test_migration_catalog_declares_budget_dependency():
    migration = next(
        item
        for item in load_migration_catalog(Path.cwd()).migrations
        if item.migration_id == "PPDB-0011"
    )
    assert migration.depends_on == ("PPDB-0010",)
    assert migration.name == "budget_governor"
