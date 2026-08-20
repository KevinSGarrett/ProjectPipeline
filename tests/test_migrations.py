from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from project_pipeline.command_center.persistence import CommandCenterStore
from project_pipeline.control.persistence import ControlStore
from project_pipeline.persistence import (
    JiraSyncStore,
    MigrationApplyHooks,
    MigrationError,
    SQLiteMigrationRunner,
    SQLiteStateStore,
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
            connection.execute("SELECT COUNT(*) FROM evidence_observations").fetchone()
        connection.execute("SELECT COUNT(*) FROM campaign_owner_bindings").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-2])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM campaign_owner_bindings").fetchone()
        connection.execute("SELECT COUNT(*) FROM campaign_runs").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-3])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM campaign_runs").fetchone()
        connection.execute("SELECT COUNT(*) FROM qualification_runs").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-4])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM qualification_runs").fetchone()
        connection.execute("SELECT COUNT(*) FROM autonomy_runtime_operations").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-5])
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
        self.assertEqual(status.applied, expected[:-6])
        connection.execute("SELECT COUNT(*) FROM lifecycle_portfolio_projects").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-7])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM lifecycle_portfolio_projects").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_director_messages").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
        connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-8])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM command_center_director_messages").fetchone()
        connection.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
        connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-9])
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
        connection.execute("SELECT COUNT(*) FROM resilience_machines").fetchone()

        status = runner.rollback_last()
        self.assertEqual(status.applied, expected[:-10])
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

    def test_checksum_mismatch_on_replay_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            runner = SQLiteMigrationRunner(connection, ROOT)
            runner.apply_all()
            connection.execute(
                "UPDATE schema_migrations SET sql_sha256 = ? WHERE migration_id = ?",
                ("0" * 64, "PPDB-0001"),
            )
            with self.assertRaises(MigrationError) as raised:
                runner.apply_all()
            self.assertIn("checksum mismatch", str(raised.exception))
            connection.close()

    def test_fault_before_ddl_leaves_empty_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            runner = SQLiteMigrationRunner(
                connection,
                ROOT,
                hooks=MigrationApplyHooks(fail_before_ddl_for="PPDB-0001"),
            )
            with self.assertRaises(MigrationError):
                runner.apply_all()
            self.assertEqual(runner.applied(), ())
            connection.close()

    def test_fault_before_receipt_rolls_back_ddl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            runner = SQLiteMigrationRunner(
                connection,
                ROOT,
                hooks=MigrationApplyHooks(fail_before_receipt_for="PPDB-0001"),
            )
            with self.assertRaises(MigrationError):
                runner.apply_all()
            self.assertEqual(runner.applied(), ())
            self.assertIsNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
                ).fetchone()
            )
            connection.close()

    def test_fault_after_ddl_rolls_back_receipt_and_objects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            runner = SQLiteMigrationRunner(
                connection,
                ROOT,
                hooks=MigrationApplyHooks(fail_after_ddl_for="PPDB-0001"),
            )
            with self.assertRaises(MigrationError):
                runner.apply_all()
            self.assertEqual(runner.applied(), ())
            self.assertIsNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
                ).fetchone()
            )
            retried = SQLiteMigrationRunner(connection, ROOT)
            status = retried.apply_all()
            self.assertIn("PPDB-0001", status.applied)
            connection.execute("SELECT COUNT(*) FROM projects").fetchone()
            connection.close()

    def test_fault_before_commit_rolls_back_receipt_insert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            runner = SQLiteMigrationRunner(
                connection,
                ROOT,
                hooks=MigrationApplyHooks(fail_before_commit_for="PPDB-0001"),
            )
            with self.assertRaises(MigrationError):
                runner.apply_all()
            self.assertEqual(runner.applied(), ())
            connection.close()

    def test_process_loss_after_ddl_is_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            ctx = multiprocessing.get_context("spawn")
            child = ctx.Process(
                target=_abort_after_first_ddl,
                args=(str(db_path), str(ROOT)),
            )
            child.start()
            child.join(timeout=60)
            self.assertIsNotNone(child.exitcode)
            self.assertNotEqual(child.exitcode, 0)
            connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            runner = SQLiteMigrationRunner(connection, ROOT)
            status = runner.apply_all()
            expected = tuple(item.migration_id for item in load_migration_catalog(ROOT).migrations)
            self.assertEqual(status.applied, expected)
            connection.close()

    def test_multiprocess_first_use_converges_without_duplicate_ddl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            ctx = multiprocessing.get_context("spawn")
            queue: multiprocessing.Queue[dict[str, object]] = ctx.Queue()
            workers = [
                ctx.Process(
                    target=_concurrent_apply_worker,
                    args=(str(db_path), str(ROOT), queue),
                )
                for _ in range(6)
            ]
            for worker in workers:
                worker.start()
            results = [queue.get(timeout=120) for _ in workers]
            for worker in workers:
                worker.join(timeout=30)
                self.assertEqual(worker.exitcode, 0)
            expected = [item.migration_id for item in load_migration_catalog(ROOT).migrations]
            self.assertTrue(all(item["ok"] for item in results), results)
            for item in results:
                self.assertEqual(item["applied"], expected)
            connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            rows = connection.execute(
                "SELECT migration_id, COUNT(*) FROM schema_migrations GROUP BY migration_id"
            ).fetchall()
            self.assertEqual({row[0] for row in rows}, set(expected))
            self.assertTrue(all(int(row[1]) == 1 for row in rows))
            connection.close()

    def test_control_jira_and_command_center_open_initialized_db_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.db"
            bootstrap = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
            SQLiteMigrationRunner(bootstrap, ROOT).apply_all()
            bootstrap.close()
            errors: list[str] = []

            def open_control() -> None:
                try:
                    with ControlStore(str(db_path), ROOT) as store:
                        store.db.execute("SELECT COUNT(*) FROM control_snapshots").fetchone()
                except Exception as exc:
                    errors.append(f"control:{exc}")

            def open_jira() -> None:
                try:
                    with JiraSyncStore(db_path, ROOT) as store:
                        store.initialize()
                        store.connection.execute(
                            "SELECT COUNT(*) FROM jira_remote_snapshots"
                        ).fetchone()
                except Exception as exc:
                    errors.append(f"jira:{exc}")

            def open_command_center() -> None:
                try:
                    with CommandCenterStore(str(db_path), ROOT) as store:
                        store.db.execute("SELECT COUNT(*) FROM command_center_events").fetchone()
                except Exception as exc:
                    errors.append(f"command_center:{exc}")

            def open_state() -> None:
                try:
                    with SQLiteStateStore(db_path, ROOT) as store:
                        store.initialize()
                        store.connection.execute("SELECT COUNT(*) FROM projects").fetchone()
                except Exception as exc:
                    errors.append(f"state:{exc}")

            threads = [
                threading.Thread(target=target)
                for target in (open_control, open_jira, open_command_center, open_state)
                for _ in range(3)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)
            self.assertEqual(errors, [])


def _concurrent_apply_worker(db_path: str, root: str, queue: multiprocessing.Queue[object]) -> None:
    last_error = ""
    for attempt in range(8):
        connection = sqlite3.connect(db_path, isolation_level=None, timeout=60.0)
        try:
            connection.execute("PRAGMA busy_timeout = 60000")
            status = SQLiteMigrationRunner(connection, Path(root)).apply_all()
            queue.put(
                {
                    "ok": True,
                    "applied": list(status.applied),
                    "pid": os.getpid(),
                }
            )
            return
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.1 * (attempt + 1))
        finally:
            connection.close()
    queue.put({"ok": False, "error": last_error, "pid": os.getpid()})


def _abort_after_first_ddl(db_path: str, root: str) -> None:
    connection = sqlite3.connect(db_path, isolation_level=None, timeout=30.0)
    SQLiteMigrationRunner(
        connection,
        Path(root),
        hooks=MigrationApplyHooks(abort_process_after_ddl_for="PPDB-0001"),
    ).apply_all()
