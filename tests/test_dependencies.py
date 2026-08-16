from __future__ import annotations

import json
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
        before = (ROOT / "requirements" / "environment.lock.json").read_bytes()
        first = build_environment_lock(ROOT)
        middle = (ROOT / "requirements" / "environment.lock.json").read_bytes()
        second = build_environment_lock(ROOT)
        after = (ROOT / "requirements" / "environment.lock.json").read_bytes()
        self.assertEqual(first, second)
        self.assertEqual(before, middle)
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
