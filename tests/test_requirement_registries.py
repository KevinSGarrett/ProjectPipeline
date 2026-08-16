from __future__ import annotations

import json
import unittest
from pathlib import Path

from project_pipeline.requirements import summarize_requirements

ROOT = Path(__file__).resolve().parents[1]


class RequirementRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requirements = [
            json.loads(line)
            for line in (ROOT / "plans/_traceability/requirements.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        cls.by_id = {item["requirement_id"]: item for item in cls.requirements}

    def test_glossary_open_decisions_and_evolution_are_complete_and_linked(self) -> None:
        glossary = json.loads(
            (ROOT / "plans/01_requirements/glossary.json").read_text(encoding="utf-8")
        )
        decisions = [
            json.loads(line)
            for line in (ROOT / "plans/01_requirements/open_decisions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        evolution = [
            json.loads(line)
            for line in (ROOT / "plans/01_requirements/source_evolution.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(glossary["term_count"], len(glossary["terms"]))
        self.assertGreaterEqual(glossary["term_count"], 60)
        self.assertEqual(len(decisions), 32)
        self.assertEqual(len(evolution), 15)
        self.assertEqual(len({item["decision_id"] for item in decisions}), len(decisions))
        self.assertEqual(len({item["record_id"] for item in evolution}), len(evolution))
        for item in [*decisions, *evolution]:
            self.assertTrue(item["linked_requirement_ids"])
            for requirement_id in item["linked_requirement_ids"]:
                self.assertIn(requirement_id, self.by_id)
        for item in decisions:
            for requirement_id in item["linked_requirement_ids"]:
                self.assertIn(item["decision_id"], self.by_id[requirement_id]["open_decision_ids"])
        for item in evolution:
            for requirement_id in item["linked_requirement_ids"]:
                self.assertIn(item["record_id"], self.by_id[requirement_id]["evolution_ids"])

    def test_generated_requirement_indexes_and_summary_are_current(self) -> None:
        by_id = json.loads(
            (ROOT / "plans/_traceability/requirements_by_id.json").read_text(encoding="utf-8")
        )
        summary = json.loads(
            (ROOT / "plans/_traceability/requirement_registry_summary.json").read_text(
                encoding="utf-8"
            )
        )
        expected_summary = summarize_requirements(self.requirements)
        expected_summary["by_state"] = expected_summary.pop("by_implementation_state")
        self.assertEqual(by_id, self.by_id)
        self.assertEqual(summary, expected_summary)
