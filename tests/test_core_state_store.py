from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_pipeline.domain import ProjectLifecycleState, TaskLifecycleState
from project_pipeline.persistence import ConcurrentStateChangeError, SQLiteStateStore
from project_pipeline.services.state import CoreStateService

ROOT = Path(__file__).resolve().parents[1]


class CoreStateStoreTests(unittest.TestCase):
    def make_store(self, directory: str) -> SQLiteStateStore:
        return SQLiteStateStore(Path(directory) / "state.db", ROOT)

    def test_repository_compiles_to_ready_project_and_all_task_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.make_store(directory) as store:
            snapshot = CoreStateService(store, ROOT).initialize_from_repository()
            self.assertEqual(snapshot["project_state"]["state"], "READY")
            expected = __import__("json").loads(
                (ROOT / "jira/BOARD_MANIFEST.json").read_text(encoding="utf-8")
            )["issue_count"]
            self.assertEqual(snapshot["task_count"], expected)
            self.assertEqual(sum(snapshot["task_counts"].values()), expected)

    def test_project_transition_uses_optimistic_versioning(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.make_store(directory) as store:
            CoreStateService(store, ROOT).initialize_from_repository()
            current = store.get_project_state("PROJECT-PIPELINE")
            assert current is not None
            updated = store.transition_project(
                project_id="PROJECT-PIPELINE",
                next_state=ProjectLifecycleState.ACTIVE,
                expected_version=current.version,
                reason="Begin controlled execution.",
                actor_id="actor:test",
                correlation_id="corr:test-project",
            )
            self.assertEqual(updated.state, ProjectLifecycleState.ACTIVE)
            with self.assertRaises(ConcurrentStateChangeError):
                store.transition_project(
                    project_id="PROJECT-PIPELINE",
                    next_state=ProjectLifecycleState.BLOCKED,
                    expected_version=current.version,
                    reason="Stale request.",
                    actor_id="actor:test",
                    correlation_id="corr:test-stale",
                    blocked_reason="Stale request should fail.",
                )

    def test_task_transition_records_immutable_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.make_store(directory) as store:
            CoreStateService(store, ROOT).initialize_from_repository()
            task = store.get_task_state("PP-TASK-000037")
            assert task is not None
            self.assertEqual(task.state, TaskLifecycleState.BACKLOG)
            updated = store.transition_task(
                task_id=task.task_id,
                next_state=TaskLifecycleState.READY,
                expected_version=task.version,
                reason="Task dependencies and prerequisites are satisfied.",
                actor_id="actor:test",
                correlation_id="corr:test-task",
            )
            history = store.list_transitions(entity_type="task", entity_id=task.task_id)
            self.assertEqual(updated.version, task.version + 1)
            self.assertEqual(history[-1].next_state, "READY")

    def test_initialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.make_store(directory) as store:
            service = CoreStateService(store, ROOT)
            first = service.initialize_from_repository()
            second = service.initialize_from_repository()
            self.assertEqual(first["task_count"], second["task_count"])
            self.assertEqual(second["project_state"]["version"], first["project_state"]["version"])

    def test_snapshot_reports_migration_and_state_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.make_store(directory) as store:
            snapshot = CoreStateService(store, ROOT).initialize_from_repository()
            self.assertEqual(snapshot["migration_status"]["pending"], [])
            self.assertIn("PPDB-0001", snapshot["migration_status"]["applied"])
