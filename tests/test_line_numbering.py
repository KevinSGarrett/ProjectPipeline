from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_pipeline.line_numbering import generate_line_numbered_plans


class LineNumberingTests(unittest.TestCase):
    def test_plan_sections_receive_exact_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plans" / "00" / "PLAN-TEST-001_example.md"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(
                "# PLAN-TEST-001 — Example\n\n## PLAN-TEST-001:SEC-01 First\n\nA\n\n## PLAN-TEST-001:SEC-02 Second\n\nB\n",
                encoding="utf-8",
            )
            (root / "plans" / "_indexes").mkdir(parents=True)
            catalog = {
                "plans": [{"plan_id": "PLAN-TEST-001", "path": "plans/00/PLAN-TEST-001_example.md"}]
            }
            (root / "plans" / "PLAN_CATALOG.json").write_text(json.dumps(catalog), encoding="utf-8")
            result = generate_line_numbered_plans(root)
            self.assertEqual(result["PLAN-TEST-001:SEC-01"]["start_line"], 3)
            self.assertEqual(result["PLAN-TEST-001:SEC-02"]["end_line"], 9)
