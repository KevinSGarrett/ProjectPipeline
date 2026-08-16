from __future__ import annotations

import json
import unittest
from pathlib import Path

from project_pipeline.traceability import coverage_summary

ROOT = Path(__file__).resolve().parents[1]


class TraceabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requirements = [
            json.loads(line)
            for line in (ROOT / "plans/_traceability/requirements.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]

    def test_requirement_ids_are_unique_and_mapped_to_plan_and_work(self) -> None:
        identifiers = [item["requirement_id"] for item in self.requirements]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertGreaterEqual(len(self.requirements), 351)
        self.assertEqual(
            sum(bool(item["plan_ids"]) for item in self.requirements), len(self.requirements)
        )
        self.assertEqual(
            sum(bool(item["jira_ids"]) for item in self.requirements), len(self.requirements)
        )

    def test_coverage_has_no_unexplained_implemented_gap(self) -> None:
        summary = coverage_summary(ROOT)
        self.assertEqual(summary["unexplained_gap_count"], 0)
        self.assertEqual(summary["mapped_counts"]["plan"], summary["requirement_count"])
        self.assertEqual(summary["mapped_counts"]["jira"], summary["requirement_count"])

    def test_traceability_exports_match_the_authoritative_catalog(self) -> None:
        expected = {item["requirement_id"]: item for item in self.requirements}
        mappings = {
            "requirements_to_plans.jsonl": "plan_ids",
            "requirements_to_jira.jsonl": "jira_ids",
            "requirements_to_implementation.jsonl": "implementation_paths",
            "requirements_to_tests.jsonl": "test_ids",
            "requirements_to_evidence.jsonl": "evidence_ids",
            "requirements_to_decisions.jsonl": "decision_ids",
            "requirements_to_open_decisions.jsonl": "open_decision_ids",
            "requirements_to_evolution.jsonl": "evolution_ids",
        }
        for filename, field in mappings.items():
            rows = [
                json.loads(line)
                for line in (ROOT / "plans/_traceability" / filename)
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual({row["requirement_id"] for row in rows}, set(expected), filename)
            for row in rows:
                self.assertEqual(
                    row[field],
                    expected[row["requirement_id"]].get(field, []),
                    (filename, row["requirement_id"]),
                )
