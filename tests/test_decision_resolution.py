from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DecisionResolutionTests(unittest.TestCase):
    def test_accepted_adrs_link_sources_requirements_components_and_tradeoffs(self) -> None:
        catalog = json.loads((ROOT / "adr/ADR_CATALOG.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["decision_count"], 27)
        for item in catalog["decisions"]:
            self.assertEqual(item["status"], "ACCEPTED")
            self.assertTrue(item["source_references"])
            self.assertTrue(item["requirement_ids"])
            self.assertTrue(item["component_ids"])
            text = (ROOT / item["path"]).read_text(encoding="utf-8")
            for heading in (
                "## Context",
                "## Decision",
                "## Alternatives considered",
                "## Consequences",
            ):
                self.assertIn(heading, text)

    def test_resolved_open_decisions_link_back_to_accepted_adrs(self) -> None:
        catalog = json.loads((ROOT / "adr/ADR_CATALOG.json").read_text(encoding="utf-8"))
        adr_ids = {item["decision_id"] for item in catalog["decisions"]}
        decisions = [
            json.loads(line)
            for line in (ROOT / "plans/01_requirements/open_decisions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        resolved = [item for item in decisions if item["status"] == "RESOLVED"]
        self.assertEqual(len(resolved), 22)
        for item in resolved:
            self.assertTrue(item["resolution"])
            self.assertTrue(item["resolved_by_decision_ids"])
            self.assertTrue(set(item["resolved_by_decision_ids"]).issubset(adr_ids))
        orchestration = next(item for item in resolved if item["decision_id"] == "OPEN-DEC-0001")
        self.assertEqual(orchestration["resolved_by_decision_ids"], ["ADR-0008"])
        self.assertIn("Hatchet", orchestration["resolution"])
        operator_protocol = next(
            item for item in resolved if item["decision_id"] == "OPEN-DEC-0028"
        )
        self.assertEqual(operator_protocol["resolved_by_decision_ids"], ["ADR-0011"])
