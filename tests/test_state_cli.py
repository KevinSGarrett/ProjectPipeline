from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from project_pipeline.cli import main

ROOT = Path(__file__).resolve().parents[1]


class StateCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*arguments, "--root", str(ROOT)])
        return code, json.loads(stdout.getvalue())

    def test_state_init_compiles_state_and_traceability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            code, payload = self.run_cli("state", "init", "--database", database)
        self.assertEqual(code, 0)
        state = payload["state"]
        self.assertEqual(state["project_state"]["state"], "READY")
        expected = __import__("json").loads(
            (ROOT / "jira/BOARD_MANIFEST.json").read_text(encoding="utf-8")
        )["issue_count"]
        self.assertEqual(state["task_count"], expected)
        self.assertEqual(state["requirement_count"], 351)
        self.assertEqual(payload["equivalence_errors"], [])

    def test_state_and_trace_queries_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            self.run_cli("state", "init", "--database", database)
            state_code, state_payload = self.run_cli("state", "status", "--database", database)
            trace_code, trace_payload = self.run_cli(
                "trace-store",
                "requirement",
                "--database",
                database,
                "--requirement-id",
                "REQ-ARCH-0008",
            )
        self.assertEqual((state_code, trace_code), (0, 0))
        self.assertEqual(state_payload["state"]["migration_status"]["pending"], [])
        self.assertEqual(trace_payload["trace"]["requirement"]["requirement_id"], "REQ-ARCH-0008")

    def test_missing_required_cli_argument_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            self.run_cli("state", "init", "--database", database)
            code, payload = self.run_cli("state", "task", "--database", database)
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "configuration_invalid")
