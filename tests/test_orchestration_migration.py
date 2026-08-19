import sqlite3

from project_pipeline.persistence.migrations import SQLiteMigrationRunner, load_migration_catalog


def test_ppdb_0010_is_catalogued_and_reversible(project_root):
    catalog = load_migration_catalog(project_root)
    migration = next(item for item in catalog.migrations if item.migration_id == "PPDB-0010")
    assert migration.depends_on == ("PPDB-0009",)

    connection = sqlite3.connect(":memory:")
    runner = SQLiteMigrationRunner(connection, project_root)
    status = runner.apply_all()
    assert status.latest_applied == "PPDB-0023"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" in tables and "orchestration_outbox" in tables
    assert "verification_runs" in tables
    assert "lifecycle_portfolio_projects" in tables
    assert "autonomy_runtime_operations" in tables

    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0022"
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0021"
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0020"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "lifecycle_portfolio_projects" in tables
    assert "autonomy_runtime_operations" in tables
    assert "qualification_runs" not in tables
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0019"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "lifecycle_portfolio_projects" in tables
    assert "autonomy_runtime_operations" not in tables

    # Remove Pass 25 audit immutability first; lifecycle state must survive.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0018"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "lifecycle_portfolio_projects" in tables

    # Remove Pass 22 lifecycle state next; the Pass 21 interaction layer must survive.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0017"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert (
        "lifecycle_portfolio_projects" not in tables
        and "command_center_director_messages" in tables
    )

    # Remove the Pass 21 interaction/delivery layer next; the Pass 19 Command Center must survive.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0016"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "command_center_events" in tables
    assert "command_center_director_messages" not in tables

    # Remove Command Center next; orchestration, Resilience, Security, and Verification must survive.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0015"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" in tables and "verification_runs" in tables
    assert "resilience_machines" in tables
    assert "command_center_events" not in tables

    # Remove Resilience next; orchestration, Security, and Verification must survive.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0014"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" in tables and "verification_runs" in tables
    assert "resilience_machines" not in tables

    # Remove Security next; orchestration and Verification must survive.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0013"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" in tables and "verification_runs" in tables

    # Remove verification, assurance and budget layers; orchestration must survive all three.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0012"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" in tables
    assert "assurance_gate_evaluations" in tables
    assert "verification_runs" not in tables

    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0011"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" in tables
    assert "assurance_gate_evaluations" not in tables

    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0010"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" in tables and "budget_limits" not in tables

    # Rolling back PPDB-0010 removes orchestration while preserving Context.
    status = runner.rollback_last()
    assert status.latest_applied == "PPDB-0009"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "orchestration_workflows" not in tables
    assert "context_packs" in tables
