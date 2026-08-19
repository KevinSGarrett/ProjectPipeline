from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from project_pipeline.persistence import (
    MigrationError,
    SQLiteMigrationRunner,
    load_migration_catalog,
    migration_catalog_fingerprint,
    validate_migration_catalog,
)

ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_catalog_is_ordered_hashed_and_current(self) -> None:
        catalog = load_migration_catalog(ROOT)
        ids = [item.migration_id for item in catalog.migrations]
        self.assertEqual(ids, [f"PPDB-{index:04d}" for index in range(1, len(ids) + 1)])
        self.assertEqual(validate_migration_catalog(ROOT), [])
        self.assertEqual(len(migration_catalog_fingerprint(ROOT)), 64)

    def test_sqlite_migrations_apply_idempotently(self) -> None:
        connection = sqlite3.connect(":memory:")
        runner = SQLiteMigrationRunner(connection, ROOT)
        first = runner.apply_all()
        second = runner.apply_all()
        expected = tuple(item.migration_id for item in load_migration_catalog(ROOT).migrations)
        self.assertEqual(first.applied, expected)
        self.assertEqual(first, second)
        connection.close()

    def test_sqlite_migrations_rollback_in_reverse_order(self) -> None:
        connection = sqlite3.connect(":memory:")
        runner = SQLiteMigrationRunner(connection, ROOT)
        runner.apply_all()
        expected = tuple(item.migration_id for item in load_migration_catalog(ROOT).migrations)

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-1])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM campaign_runs").fetchone()
        connection.execute("SELECT COUNT(*) FROM qualification_runs").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-2])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM qualification_runs").fetchone()
        connection.execute("SELECT COUNT(*) FROM autonomy_runtime_operations").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-3])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM autonomy_runtime_operations").fetchone()
        connection.execute("SELECT COUNT(*) FROM jira_sync_operations").fetchone()
        connection.execute("SELECT COUNT(*) FROM github_operations").fetchone()
        connection.execute("SELECT COUNT(*) FROM scheduler_resource_pools").fetchone()
        connection.execute("SELECT COUNT(*) FROM agent_registry_snapshots").fetchone()
        connection.execute("SELECT COUNT(*) FROM context_packs").fetchone()
        connection.execute("SELECT COUNT(*) FROM orchestration_workflows").fetchone()
        connection.execute("SELECT COUNT(*) FROM budget_limits").fetchone()
        connection.execute("SELECT COUNT(*) FROM assurance_gate_evaluations").fetchone()
        connection.execute("SELECT COUNT(*) FROM verification_runs").fetchone()
        connection.execute("SELECT COUNT(*) FROM security_identities").fetchone()
        connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_director_messages").fetchone()
        connection.execute("SELECT COUNT(*) FROM lifecycle_portfolio_projects").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-4])
        connection.execute("SELECT COUNT(*) FROM lifecycle_portfolio_projects").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-5])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM lifecycle_portfolio_projects").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_director_messages").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
        connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-6])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM command_center_director_messages").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
        connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-7])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
        connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-8])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()
        connection.execute("SELECT COUNT(*) FROM security_identities").fetchone()
        connection.close()

    def test_failed_migration_rolls_back_only_its_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "database", root / "database")
            catalog_path = root / "database" / "MIGRATION_CATALOG.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            second_path = root / catalog["migrations"][1]["sqlite_up_path"]
            second_path.write_text(
                "CREATE TABLE partial_state(id INTEGER);\nINVALID SQL;\n", encoding="utf-8"
            )
            connection = sqlite3.connect(":memory:")
            runner = SQLiteMigrationRunner(connection, root)
            with self.assertRaises(MigrationError):
                runner.apply_all()
            self.assertEqual(runner.applied(), ("PPDB-0001",))
            self.assertIsNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='partial_state'"
                ).fetchone()
            )
            connection.close()
