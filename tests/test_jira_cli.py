from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from project_pipeline.cli import main

ROOT = Path(__file__).resolve().parents[1]


class JiraCliTests(unittest.TestCase):
    def _run(self, arguments):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(arguments)
        return code, json.loads(stream.getvalue())

    def test_validate_and_export_import_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exported = Path(directory) / "jira.json"
            code, validation = self._run(["jira", "validate", "--root", str(ROOT)])
            self.assertEqual(code, 0)
            self.assertTrue(validation["valid"])
            code, result = self._run(
                ["jira", "export", "--root", str(ROOT), "--output", str(exported)]
            )
            self.assertEqual(code, 0)
            expected = json.loads((ROOT / "jira/BOARD_MANIFEST.json").read_text(encoding="utf-8"))[
                "issue_count"
            ]
            self.assertEqual(result["issue_count"], expected)
            code, diff = self._run(
                [
                    "jira",
                    "import-diff",
                    "--root",
                    str(ROOT),
                    "--database",
                    str(Path(directory) / "state.db"),
                    "--input",
                    str(exported),
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue(diff["safe_to_import"])

    def test_sync_defaults_to_dry_run_and_requires_explicit_apply_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "jira.db"
            code, result = self._run(
                [
                    "jira",
                    "sync",
                    "--root",
                    str(ROOT),
                    "--database",
                    str(database),
                    "--provider",
                    "mock",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(result["receipt"]["result"], "DRY_RUN")
            expected = json.loads((ROOT / "jira/BOARD_MANIFEST.json").read_text(encoding="utf-8"))[
                "issue_count"
            ]
            create_operations = [
                operation
                for operation in result["plan"]["operations"]
                if operation["operation_type"] == "CREATE_REMOTE_ISSUE"
            ]
            self.assertEqual(len(create_operations), expected)
            self.assertTrue(
                any(
                    operation["operation_type"] == "CREATE_REMOTE_LINK"
                    for operation in result["plan"]["operations"]
                )
            )

            code, rejected = self._run(
                [
                    "jira",
                    "sync",
                    "--root",
                    str(ROOT),
                    "--database",
                    str(database),
                    "--provider",
                    "mock",
                    "--apply",
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("--approve", rejected["message"])

    def test_comment_is_dry_run_until_apply_is_explicit(self) -> None:
        code, result = self._run(
            [
                "jira",
                "comment",
                "--root",
                str(ROOT),
                "--provider",
                "mock",
                "--database",
                ":memory:",
                "--local-id",
                "PP-EPIC-000001",
                "--comment-kind",
                "DECISION",
                "--comment-body",
                "Decision: preserve source-controlled Jira identities and reconcile remote state through the steward.",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["mode"], "DRY_RUN")
        self.assertTrue(result["comment_intent"]["comment_intent_id"].startswith("JCOM-"))
