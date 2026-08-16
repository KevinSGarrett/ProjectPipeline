from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureCliTests(unittest.TestCase):
    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "project_pipeline", *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_summary_and_component_queries(self) -> None:
        summary = self._run("architecture", "--root", ".", "--summary")
        self.assertEqual(0, summary.returncode, summary.stderr)
        self.assertEqual(35, json.loads(summary.stdout)["component_count"])
        component = self._run("architecture", "--root", ".", "--component", "COMP-CTRL-001")
        self.assertEqual(0, component.returncode, component.stderr)
        self.assertEqual("COMP-CTRL-001", json.loads(component.stdout)[0]["component_id"])


if __name__ == "__main__":
    unittest.main()
