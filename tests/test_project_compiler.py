from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_pipeline.domain import IntakeMode, ProjectIntakeRequest, ProjectProfile
from project_pipeline.intake import (
    compile_project,
    validate_intake_foundation,
    write_compilation_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
PYTHON_FIXTURE = ROOT / "fixtures/intake/existing_python_service"
POLYGLOT_FIXTURE = ROOT / "fixtures/intake/polyglot_application"


class ProjectCompilerTests(unittest.TestCase):
    def test_compilation_is_deterministic_for_unchanged_repository_semantics(self) -> None:
        request = ProjectIntakeRequest(
            mode=IntakeMode.EXISTING_PROJECT,
            project_name="Example Service",
            target_root=str(PYTHON_FIXTURE),
        )
        first = compile_project(request)
        second = compile_project(request)
        self.assertEqual(first.compilation_id, second.compilation_id)
        self.assertEqual(first.semantic_fingerprint(), second.semantic_fingerprint())
        self.assertNotEqual(first.compiled_at_utc, second.compiled_at_utc)

    def test_compiler_selects_python_service_and_builds_enriched_repository_map(self) -> None:
        manifest = compile_project(
            ProjectIntakeRequest(
                mode=IntakeMode.EXISTING_PROJECT,
                project_name="Example Service",
                target_root=str(PYTHON_FIXTURE),
            )
        )
        self.assertEqual(manifest.primary_profile, ProjectProfile.PYTHON_SERVICE)
        self.assertGreater(manifest.repository_map.file_count, 5)
        entry = next(
            item for item in manifest.repository_map.entries if item.path.endswith("api.py")
        )
        self.assertIn("health", entry.symbols)
        self.assertIn("tests/test_api.py", entry.tested_by)
        self.assertIn("product_behavior", entry.change_relevance)

    def test_polyglot_profile_activates_cross_component_policy(self) -> None:
        manifest = compile_project(
            ProjectIntakeRequest(
                mode=IntakeMode.EXISTING_PROJECT,
                project_name="Polyglot",
                target_root=str(POLYGLOT_FIXTURE),
            )
        )
        self.assertEqual(manifest.primary_profile, ProjectProfile.POLYGLOT_APPLICATION)
        self.assertIn(ProjectProfile.WEB_APPLICATION, manifest.profiles)
        self.assertIn(ProjectProfile.PYTHON_SERVICE, manifest.profiles)

    def test_existing_project_gap_report_preserves_non_destructive_adoption_rule(self) -> None:
        manifest = compile_project(
            ProjectIntakeRequest(
                mode=IntakeMode.EXISTING_PROJECT,
                project_name="Example Service",
                target_root=str(PYTHON_FIXTURE),
            )
        )
        titles = {gap.title for gap in manifest.gap_report.gaps}
        self.assertIn("Existing-project adoption remains non-destructive", titles)
        self.assertIn("DISCOVERY_IS_READ_ONLY", manifest.operating_constraints)
        self.assertIn("SRC-017:L001122-L001175", manifest.source_authorities)

    def test_greenfield_compilation_uses_requested_profile_and_bootstrap_gap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-project"
            manifest = compile_project(
                ProjectIntakeRequest(
                    mode=IntakeMode.NEW_PROJECT,
                    project_name="New Service",
                    target_root=str(target),
                    requested_profiles=(ProjectProfile.PYTHON_SERVICE,),
                )
            )
        self.assertEqual(manifest.primary_profile, ProjectProfile.PYTHON_SERVICE)
        self.assertIn(ProjectProfile.EMPTY, manifest.profiles)
        self.assertEqual(manifest.repository_map.file_count, 0)
        self.assertTrue(any(gap.bootstrap_eligible for gap in manifest.gap_report.gaps))

    def test_repository_intake_foundation_self_validation_is_clean(self) -> None:
        self.assertEqual(validate_intake_foundation(ROOT), [])

    def test_compilation_bundle_is_idempotent_and_refuses_unapproved_replacement(self) -> None:
        manifest = compile_project(
            ProjectIntakeRequest(
                mode=IntakeMode.EXISTING_PROJECT,
                project_name="Example Service",
                target_root=str(PYTHON_FIXTURE),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = write_compilation_bundle(manifest, output)
            second = write_compilation_bundle(manifest, output)
            self.assertTrue(all(value == "WRITTEN" for value in first.values()))
            self.assertTrue(all(value == "UNCHANGED" for value in second.values()))
            path = output / "compilation_summary.json"
            path.write_text(json.dumps({"tampered": True}), encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_compilation_bundle(manifest, output)
