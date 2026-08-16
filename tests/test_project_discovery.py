from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from project_pipeline.domain import DiscoveryArtifactKind, IntakeMode, ProjectIntakeRequest
from project_pipeline.intake import DiscoveryError, discover_repository

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/intake/existing_python_service"


class ProjectDiscoveryTests(unittest.TestCase):
    def request(self, root: Path, **changes: object) -> ProjectIntakeRequest:
        values: dict[str, object] = {
            "mode": IntakeMode.EXISTING_PROJECT,
            "project_name": "Example Service",
            "target_root": str(root),
        }
        values.update(changes)
        return ProjectIntakeRequest(**values)

    def test_discovers_instructions_plans_jira_requirements_and_build_metadata(self) -> None:
        discovery = discover_repository(self.request(FIXTURE))
        roles = {item.role for item in discovery.files}
        self.assertIn(DiscoveryArtifactKind.INSTRUCTION, roles)
        self.assertIn(DiscoveryArtifactKind.PLAN, roles)
        self.assertIn(DiscoveryArtifactKind.JIRA, roles)
        self.assertIn(DiscoveryArtifactKind.REQUIREMENT, roles)
        self.assertIn("python:pyproject", discovery.build_systems)
        self.assertIn("python -m pytest", discovery.test_commands)
        self.assertIn("github-actions", discovery.deployment_surfaces)

    def test_discovers_symbols_dependencies_test_links_and_owners_without_execution(self) -> None:
        discovery = discover_repository(self.request(FIXTURE))
        api = next(item for item in discovery.files if item.path.endswith("api.py"))
        self.assertIn("Health", api.symbols)
        self.assertIn("health", api.symbols)
        self.assertIn("pydantic", api.dependencies)
        self.assertIn("tests/test_api.py", api.tested_by)

    def test_external_symlink_is_recorded_and_never_traversed(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            outside = Path(external) / "outside.py"
            outside.write_text("SECRET = 'not inspected'\n", encoding="utf-8")
            try:
                os.symlink(outside, root / "linked.py")
            except OSError:
                self.skipTest("symbolic links are unavailable in this environment")
            discovery = discover_repository(self.request(root))
            self.assertEqual(len(discovery.symlinks), 1)
            self.assertFalse(discovery.symlinks[0].target_within_root)
            self.assertIn("linked.py", discovery.boundary_violations)
            self.assertEqual(discovery.files, ())

    def test_nested_repository_is_boundary_violation_unless_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "vendor"
            (nested / ".git").mkdir(parents=True)
            (nested / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
            denied = discover_repository(self.request(root))
            self.assertIn("nested-repository:vendor", denied.boundary_violations)
            self.assertFalse(any(item.path == "vendor/source.py" for item in denied.files))
            allowed = discover_repository(self.request(root, allow_nested_repositories=True))
            self.assertTrue(any(item.path == "vendor/source.py" for item in allowed.files))
            self.assertEqual(len(allowed.repositories), 2)

    def test_discovery_limits_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("one", encoding="utf-8")
            (root / "two.txt").write_text("two", encoding="utf-8")
            with self.assertRaises(DiscoveryError):
                discover_repository(self.request(root, max_files=1))
            with self.assertRaises(DiscoveryError):
                discover_repository(self.request(root, max_total_bytes=1))

    def test_malformed_build_declarations_are_diagnostics_not_code_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project\ninvalid", encoding="utf-8")
            (root / "package.json").write_text("{invalid", encoding="utf-8")
            discovery = discover_repository(self.request(root))
            self.assertTrue(
                any("pyproject.toml is not parseable" in item for item in discovery.diagnostics)
            )
            self.assertTrue(
                any("package.json is not parseable" in item for item in discovery.diagnostics)
            )

    def test_existing_project_requires_a_directory_but_new_project_may_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with self.assertRaises(DiscoveryError):
                discover_repository(self.request(missing))
            discovery = discover_repository(
                ProjectIntakeRequest(
                    mode=IntakeMode.NEW_PROJECT,
                    project_name="Greenfield",
                    target_root=str(missing),
                )
            )
            self.assertEqual(discovery.files, ())
            self.assertEqual(discovery.root_path, str(missing.resolve()))
