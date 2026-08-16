from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from project_pipeline.domain import (
    BootstrapOutcome,
    IntakeMode,
    ProjectIntakeRequest,
    ProjectProfile,
)
from project_pipeline.intake import compile_project, execute_bootstrap, plan_bootstrap


class ProjectBootstrapTests(unittest.TestCase):
    def test_greenfield_dry_run_does_not_create_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-service"
            manifest = compile_project(
                ProjectIntakeRequest(
                    mode=IntakeMode.NEW_PROJECT,
                    project_name="New Service",
                    target_root=str(target),
                    requested_profiles=(ProjectProfile.PYTHON_SERVICE,),
                )
            )
            plan, receipt = execute_bootstrap(manifest, apply=False)
            self.assertEqual(receipt.outcome, BootstrapOutcome.DRY_RUN)
            self.assertFalse(target.exists())
            self.assertFalse(plan.destructive_actions)

    def test_greenfield_apply_creates_profile_files_and_replay_is_no_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-service"
            manifest = compile_project(
                ProjectIntakeRequest(
                    mode=IntakeMode.NEW_PROJECT,
                    project_name="New Service",
                    target_root=str(target),
                    requested_profiles=(ProjectProfile.PYTHON_SERVICE,),
                )
            )
            _, first = execute_bootstrap(manifest, apply=True)
            _, second = execute_bootstrap(manifest, apply=True)
            self.assertEqual(first.outcome, BootstrapOutcome.APPLIED)
            self.assertEqual(second.outcome, BootstrapOutcome.NO_CHANGES)
            self.assertTrue((target / "pyproject.toml").is_file())
            self.assertTrue((target / ".project-pipeline/project_manifest.json").is_file())
            self.assertTrue((target / ".github/workflows/ci.yml").is_file())

    def test_existing_project_requires_confirmation_and_preserves_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            readme = target / "README.md"
            readme.write_text("# Human Authored\n", encoding="utf-8")
            manifest = compile_project(
                ProjectIntakeRequest(
                    mode=IntakeMode.EXISTING_PROJECT,
                    project_name="Adopted",
                    target_root=str(target),
                )
            )
            _, rejected = execute_bootstrap(manifest, apply=True, confirm_existing=False)
            self.assertEqual(rejected.outcome, BootstrapOutcome.REJECTED)
            _, applied = execute_bootstrap(manifest, apply=True, confirm_existing=True)
            self.assertEqual(applied.outcome, BootstrapOutcome.APPLIED)
            self.assertEqual(readme.read_text(encoding="utf-8"), "# Human Authored\n")
            self.assertTrue((target / "instruction/README.md").is_file())
            self.assertFalse((target / ".github/workflows/ci.yml").exists())

    def test_conflicting_authority_file_rejects_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            instruction = target / "instruction"
            instruction.mkdir()
            authority = instruction / "README.md"
            authority.write_text("# Existing Authority\n", encoding="utf-8")
            manifest = compile_project(
                ProjectIntakeRequest(
                    mode=IntakeMode.EXISTING_PROJECT,
                    project_name="Adopted",
                    target_root=str(target),
                )
            )
            plan = plan_bootstrap(manifest)
            self.assertTrue(
                any(
                    item.path == "instruction/README.md" and item.action.value == "CONFLICT"
                    for item in plan.actions
                )
            )
            _, receipt = execute_bootstrap(manifest, apply=True, confirm_existing=True)
            self.assertEqual(receipt.outcome, BootstrapOutcome.REJECTED)
            self.assertEqual(authority.read_text(encoding="utf-8"), "# Existing Authority\n")

    def test_failed_write_rolls_back_created_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-service"
            manifest = compile_project(
                ProjectIntakeRequest(
                    mode=IntakeMode.NEW_PROJECT,
                    project_name="Rollback Service",
                    target_root=str(target),
                    requested_profiles=(ProjectProfile.PYTHON_SERVICE,),
                )
            )
            from project_pipeline.intake import bootstrap as module

            original = module._write_exclusive
            calls = {"count": 0}

            def fail_second(path: Path, content: str) -> None:
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("simulated write failure")
                original(path, content)

            with patch.object(module, "_write_exclusive", side_effect=fail_second):
                _, receipt = execute_bootstrap(manifest, apply=True)
            self.assertEqual(receipt.outcome, BootstrapOutcome.ROLLED_BACK)
            self.assertFalse(any(path.is_file() for path in target.rglob("*") if target.exists()))
