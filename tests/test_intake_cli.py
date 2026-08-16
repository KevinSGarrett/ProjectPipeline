from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from project_pipeline.cli import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/intake/existing_python_service"


class IntakeCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*arguments, "--root", str(ROOT)])
        self.assertTrue(stdout.getvalue(), stderr.getvalue())
        return code, json.loads(stdout.getvalue())

    def test_inspect_is_read_only_and_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            code, payload = self.run_cli(
                "intake",
                "inspect",
                "--target-root",
                str(FIXTURE),
                "--mode",
                "EXISTING_PROJECT",
                "--project-name",
                "Example Service",
                "--database",
                database,
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["summary"]["instruction_count"], 1)
            self.assertFalse(Path(database).exists())

    def test_compile_persist_status_and_bundle_are_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            bundle = Path(directory) / "bundle"
            code, payload = self.run_cli(
                "intake",
                "compile",
                "--target-root",
                str(FIXTURE),
                "--mode",
                "EXISTING_PROJECT",
                "--project-name",
                "Example Service",
                "--database",
                database,
                "--bundle-dir",
                str(bundle),
            )
            compilation_id = payload["compilation"]["compilation_id"]
            status_code, status = self.run_cli(
                "intake",
                "status",
                "--database",
                database,
                "--compilation-id",
                compilation_id,
            )
            self.assertEqual((code, status_code), (0, 0))
            self.assertTrue(status["found"])
            self.assertTrue((bundle / "compiled_project_manifest.json").is_file())

    def test_existing_bootstrap_without_confirmation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "existing"
            target.mkdir()
            (target / "README.md").write_text("# Existing\n", encoding="utf-8")
            code, payload = self.run_cli(
                "intake",
                "bootstrap",
                "--target-root",
                str(target),
                "--mode",
                "EXISTING_PROJECT",
                "--project-name",
                "Existing",
                "--database",
                str(Path(directory) / "state.db"),
                "--apply",
            )
            self.assertEqual(code, 1)
            self.assertEqual(payload["receipt"]["outcome"], "REJECTED")
            self.assertFalse((target / "instruction/README.md").exists())

    def test_missing_intake_arguments_return_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, payload = self.run_cli(
                "intake",
                "compile",
                "--database",
                str(Path(directory) / "state.db"),
            )
        self.assertEqual(code, 2)
        self.assertIn("required", payload["message"])
