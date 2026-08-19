import sqlite3
from pathlib import Path

from project_pipeline.domain.verification import (
    ToolActivationState,
    VerificationToolActivation,
    verification_identifier,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner
from project_pipeline.verification.persistence import VerificationStore


def test_verification_store_roundtrip_activation(project_root: Path, tmp_path: Path):
    db = tmp_path / "verification.db"
    value = VerificationToolActivation(
        activation_id=verification_identifier("VTOOL", "UPSTREAM-063", "ADAPTER"),
        upstream_id="UPSTREAM-063",
        repository="microsoft/playwright",
        state=ToolActivationState.ADAPTER_IMPLEMENTED,
        installed_version="1.57.0",
        integration_paths=("src/project_pipeline/verification/browser.py",),
        activation_phase="PASS16",
        reason="adapter",
        license="Apache-2.0",
    )
    with VerificationStore(db, project_root) as store:
        store.save_activation("PROJECT-PIPELINE", value)
        assert store.list_activations("PROJECT-PIPELINE") == (value,)


def test_ppdb_0013_is_reversible_without_damaging_ppdb_0012(project_root: Path):
    conn = sqlite3.connect(":memory:")
    runner = SQLiteMigrationRunner(conn, project_root)
    runner.apply_all()
    assert runner.status().latest_applied == "PPDB-0024"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0022"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0021"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0020"
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0019"
    # Pass 25 audit immutability rolls back first without damaging lifecycle state.
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0018"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name='lifecycle_portfolio_projects'"
    ).fetchone()
    # Pass 22 lifecycle state rolls back next without damaging Pass 21 interaction state.
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0017"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name='command_center_director_messages'"
    ).fetchone()
    assert (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE name='lifecycle_portfolio_projects'"
        ).fetchone()
        is None
    )
    # Pass 21 interaction/delivery state rolls back next without damaging Command Center.
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0016"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name='command_center_events'"
    ).fetchone()
    assert (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE name='command_center_director_messages'"
        ).fetchone()
        is None
    )
    # Command Center rolls back next without damaging Resilience, Security, or Verification.
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0015"
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='verification_runs'").fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name='resilience_machines'"
    ).fetchone()
    assert (
        conn.execute("SELECT name FROM sqlite_master WHERE name='command_center_events'").fetchone()
        is None
    )
    # Resilience then rolls back without damaging Security or Verification.
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0014"
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='verification_runs'").fetchone()
    assert (
        conn.execute("SELECT name FROM sqlite_master WHERE name='resilience_machines'").fetchone()
        is None
    )
    # Security then rolls back without damaging Verification.
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0013"
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='verification_runs'").fetchone()
    # Verification then rolls back cleanly to Assurance.
    runner.rollback_last()
    assert runner.status().latest_applied == "PPDB-0012"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name='assurance_gate_evaluations'"
    ).fetchone()
    assert (
        conn.execute("SELECT name FROM sqlite_master WHERE name='verification_runs'").fetchone()
        is None
    )
