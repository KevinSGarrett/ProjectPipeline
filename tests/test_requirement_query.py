from __future__ import annotations

import unittest
from pathlib import Path

from project_pipeline.requirements import (
    find_requirements,
    requirement_index,
    summarize_requirements,
)

ROOT = Path(__file__).resolve().parents[1]


class RequirementQueryTests(unittest.TestCase):
    def test_query_filters_are_composable_and_case_normalized(self) -> None:
        rows = find_requirements(ROOT, domain="sec", priority="p0", text="secret")
        self.assertTrue(rows)
        self.assertTrue(all(row["domain"] == "SEC" and row["priority"] == "P0" for row in rows))
        source_rows = find_requirements(ROOT, source_id="SRC-018")
        self.assertEqual(source_rows, [])
        self.assertTrue(find_requirements(ROOT, source_id="SRC-017"))

    def test_requirement_index_and_summary_match_catalog(self) -> None:
        index = requirement_index(ROOT)
        summary = summarize_requirements(index.values())
        self.assertEqual(summary["requirement_count"], len(index))
        self.assertEqual(sum(summary["by_domain"].values()), len(index))
        self.assertIn("REQ-REQ-0005", index)
