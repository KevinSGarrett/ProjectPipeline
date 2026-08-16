from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from project_pipeline.dependencies import (
    build_environment_lock,
    dependency_snapshot,
    validate_dependency_lock,
)

ROOT = Path(__file__).resolve().parents[1]


class DependencyTests(unittest.TestCase):
    def test_observed_environment_lock_and_exports_are_current(self) -> None:
        self.assertEqual(validate_dependency_lock(ROOT, verify_installed=True), [])
        snapshot = dependency_snapshot(ROOT)
        self.assertEqual(snapshot["lock_kind"], "OBSERVED_ENVIRONMENT")
        self.assertGreaterEqual(snapshot["locked_package_count"], 3)

    def test_lock_generation_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements").mkdir()
            (root / "config").mkdir()
            shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
            shutil.copy2(
                ROOT / "config" / "dependency_policy.json",
                root / "config" / "dependency_policy.json",
            )
            first = build_environment_lock(root)
            middle = (root / "requirements" / "environment.lock.json").read_bytes()
            second = build_environment_lock(root)
            after = (root / "requirements" / "environment.lock.json").read_bytes()
        self.assertEqual(first, second)
        self.assertEqual(middle, after)

    def test_missing_active_dependency_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements").mkdir()
            (root / "config").mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nname="sample"\nversion="0.0.1"\ndependencies=["missing-package>=1"]\n',
                encoding="utf-8",
            )
            (root / "config" / "dependency_policy.json").write_text(
                json.dumps(
                    {
                        "active_lock_groups": ["runtime"],
                        "resolver_lock": {
                            "manager": "uv",
                            "state": "BLOCKED_EXTERNAL",
                            "blocker": "offline",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "requirements" / "environment.lock.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "lock_kind": "OBSERVED_ENVIRONMENT",
                        "active_groups": ["runtime"],
                        "package_count": 0,
                        "packages": [],
                        "closure": {"runtime": []},
                    }
                ),
                encoding="utf-8",
            )
            errors = validate_dependency_lock(root)
        self.assertTrue(any("missing-package" in error for error in errors))

    def test_stale_quality_tool_export_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements").mkdir()
            (root / "config").mkdir()
            shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
            shutil.copy2(
                ROOT / "config" / "dependency_policy.json",
                root / "config" / "dependency_policy.json",
            )
            for name in (
                "environment.lock.json",
                "runtime.txt",
                "development.txt",
                "quality-tools.txt",
            ):
                shutil.copy2(ROOT / "requirements" / name, root / "requirements" / name)
            (root / "requirements" / "quality-tools.txt").write_text(
                "ruff==0.16.3\n", encoding="utf-8"
            )
            errors = validate_dependency_lock(root)
        self.assertIn(
            "quality-tool intent export is stale: requirements/quality-tools.txt",
            errors,
        )

    def test_quality_policy_must_match_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements").mkdir()
            (root / "config").mkdir()
            shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
            policy = json.loads(
                (ROOT / "config" / "dependency_policy.json").read_text(encoding="utf-8")
            )
            policy["quality_tool_intents"] = policy["quality_tool_intents"][:-1]
            (root / "config" / "dependency_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            for name in (
                "environment.lock.json",
                "runtime.txt",
                "development.txt",
                "quality-tools.txt",
            ):
                shutil.copy2(ROOT / "requirements" / name, root / "requirements" / name)
            errors = validate_dependency_lock(root)
        self.assertIn(
            "pyproject quality group differs from dependency policy intents",
            errors,
        )
