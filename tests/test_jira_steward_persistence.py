from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from project_pipeline.domain.jira import (
    JiraAuthorityMode,
    JiraOperationState,
    JiraReconciliationPlan,
    JiraRemoteSnapshot,
    JiraSyncOperation,
    JiraSyncOperationType,
    JiraSyncReceipt,
    jira_sync_identifier,
)
from project_pipeline.jira_steward.persistence import JiraSyncPersistenceError, JiraSyncStore
from project_pipeline.jira_steward.repository import JiraMirrorRepository
from project_pipeline.persistence import SQLiteMigrationRunner

ROOT = Path(__file__).resolve().parents[1]


class JiraStewardPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:", isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.store = JiraSyncStore(self.connection, ROOT)
        self.store.initialize()
        self.snapshot = JiraRemoteSnapshot.create(project_key="PP", issues=())
        self.store.put_snapshot(self.snapshot)
        local = JiraMirrorRepository(ROOT).bundle()
        operation = JiraSyncOperation.create(
            operation_type=JiraSyncOperationType.NO_OPERATION,
            local_id=local.issues[0].local_id,
            remote_key=None,
            payload={"reason": "already converged"},
        )
        self.plan = JiraReconciliationPlan(
            plan_id=jira_sync_identifier("JPLAN", "persistence-test", operation.operation_id),
            project_key="PP",
            authority_mode=JiraAuthorityMode.SOURCE_CONTROLLED_LOCAL,
            local_fingerprint=local.fingerprint,
            remote_snapshot_id=self.snapshot.snapshot_id,
            remote_fingerprint=self.snapshot.fingerprint,
            operations=(operation,),
            conflicts=(),
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_latest_migration_contains_jira_sync_tables(self) -> None:
        status = SQLiteMigrationRunner(self.connection, ROOT).status()
        self.assertIn("PPDB-0004", status.applied)
        self.assertIn("PPDB-0004", status.applied)
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("jira_sync_operations", tables)
        self.assertIn("jira_remote_mappings", tables)

    def test_plan_and_operation_state_are_persisted_idempotently(self) -> None:
        self.store.put_plan(self.plan)
        self.store.put_plan(self.plan)
        operation = self.plan.operations[0]
        self.assertEqual(
            self.store.operation_state(operation.operation_id), JiraOperationState.PLANNED
        )
        self.store.set_operation_state(operation.operation_id, JiraOperationState.APPLIED)
        self.assertEqual(
            self.store.operation_state(operation.operation_id), JiraOperationState.APPLIED
        )
        self.assertEqual(self.store.list_outbox(), ())

    def test_remote_mapping_rejects_split_identity(self) -> None:
        self.store.put_remote_mapping(
            local_id="PP-TASK-000001",
            remote_key="PP-1",
            provider_id="mock-jira",
            source_operation_id=None,
            remote_fingerprint="a" * 64,
        )
        with self.assertRaises(JiraSyncPersistenceError):
            self.store.put_remote_mapping(
                local_id="PP-TASK-000001",
                remote_key="PP-2",
                provider_id="mock-jira",
                source_operation_id=None,
                remote_fingerprint="b" * 64,
            )

    def test_receipt_round_trip(self) -> None:
        self.store.put_plan(self.plan)
        receipt = JiraSyncReceipt(
            receipt_id=jira_sync_identifier("JREC", self.plan.plan_id, "dry"),
            plan_id=self.plan.plan_id,
            mode="DRY_RUN",
            result="DRY_RUN",
            conflict_ids=(),
            actor_id="actor:test",
            correlation_id="corr:test",
        )
        self.store.put_receipt(receipt)
        self.assertEqual(self.store.get_receipt(receipt.receipt_id), receipt)
