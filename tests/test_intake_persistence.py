from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_pipeline.domain import IntakeMode, ProjectIntakeRequest
from project_pipeline.persistence import SQLiteStateStore
from project_pipeline.services import ProjectIntakeService

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/intake/existing_python_service"


class IntakePersistenceTests(unittest.TestCase):
    def test_compilation_persists_idempotently_with_third_migration(self) -> None:
        request = ProjectIntakeRequest(
            mode=IntakeMode.EXISTING_PROJECT,
            project_name="Example Service",
            target_root=str(FIXTURE),
        )
        with tempfile.TemporaryDirectory() as directory:  # noqa: SIM117 - store path depends on directory
            with SQLiteStateStore(Path(directory) / "state.db", ROOT) as store:
                service = ProjectIntakeService(store)
                first, first_result = service.compile(request)
                second, second_result = service.compile(request)
                self.assertEqual(first.compilation_id, second.compilation_id)
                self.assertTrue(first_result and first_result["changed"])
                self.assertFalse(second_result and second_result["changed"])
                self.assertIn("PPDB-0003", store.migration_status()["applied"])

    def test_status_queries_compilation_and_bootstrap_receipts(self) -> None:
        request = ProjectIntakeRequest(
            mode=IntakeMode.EXISTING_PROJECT,
            project_name="Example Service",
            target_root=str(FIXTURE),
        )
        with tempfile.TemporaryDirectory() as directory:  # noqa: SIM117 - store path depends on directory
            with SQLiteStateStore(Path(directory) / "state.db", ROOT) as store:
                service = ProjectIntakeService(store)
                manifest, _ = service.compile(request)
                service.bootstrap(
                    manifest,
                    apply=False,
                    confirm_existing=True,
                    actor_id="actor:test",
                    correlation_id="corr:test",
                )
                result = service.status(compilation_id=manifest.compilation_id)
                self.assertTrue(result["found"])
                self.assertEqual(len(result["bootstrap_receipts"]), 1)
                self.assertEqual(result["bootstrap_receipts"][0]["outcome"], "DRY_RUN")

    def test_project_status_lists_only_requested_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:  # noqa: SIM117 - store path depends on directory
            with SQLiteStateStore(Path(directory) / "state.db", ROOT) as store:
                service = ProjectIntakeService(store)
                manifest, _ = service.compile(
                    ProjectIntakeRequest(
                        mode=IntakeMode.EXISTING_PROJECT,
                        project_name="Example Service",
                        target_root=str(FIXTURE),
                    )
                )
                found = service.status(project_id=manifest.project_id)
                missing = service.status(project_id="PROJECT-NOT-PRESENT")
                self.assertEqual(found["compilation_count"], 1)
                self.assertFalse(missing["found"])
