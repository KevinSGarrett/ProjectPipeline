from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from project_pipeline.cli import main

ROOT = Path(__file__).resolve().parents[1]


class FoundationCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            return_code = main([*arguments, "--root", str(ROOT)])
        return return_code, json.loads(stdout.getvalue())

    def test_config_validate_outputs_fingerprint_and_sources(self) -> None:
        return_code, payload = self.run_cli("config", "validate", "--profile", "local")
        self.assertEqual(return_code, 0)
        self.assertEqual(len(str(payload["fingerprint"])), 64)
        self.assertEqual(payload["settings"]["profile"], "local")

    def test_schema_and_dependency_checks_are_executable(self) -> None:
        schema_code, schema_payload = self.run_cli("schemas", "check")
        dependency_code, dependency_payload = self.run_cli(
            "dependencies", "validate", "--verify-installed"
        )
        self.assertEqual((schema_code, dependency_code), (0, 0))
        self.assertEqual(schema_payload["errors"], [])
        self.assertEqual(dependency_payload["errors"], [])

    def test_doctor_reports_non_blocked_local_state(self) -> None:
        return_code, payload = self.run_cli("doctor", "--profile", "local")
        self.assertEqual(return_code, 0)
        self.assertTrue(payload["ok"])
        self.assertNotEqual(payload["state"], "BLOCKED")
