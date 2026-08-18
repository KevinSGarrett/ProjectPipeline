from __future__ import annotations

import json
import unittest
from pathlib import Path

from project_pipeline.ids import REQUIREMENT_ID

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {
    "PDEF",
    "REQ",
    "ARCH",
    "CTRL",
    "SCHED",
    "CTX",
    "AGENT",
    "GOV",
    "ASSURE",
    "SEC",
    "BUDGET",
    "RES",
    "UX",
    "OPS",
    "INFRA",
    "LIFE",
    "UPSTREAM",
    "REL",
}
REQUIRED_FIELDS = {
    "schema_version",
    "requirement_id",
    "domain",
    "title",
    "statement",
    "requirement_type",
    "normative_strength",
    "authority_classification",
    "source_references",
    "source_sequence",
    "rationale",
    "priority",
    "risk",
    "disposition",
    "disposition_reason",
    "implementation_state",
    "plan_ids",
    "plan_section_ids",
    "jira_ids",
    "verification_class",
    "verification_expectation",
    "acceptance_summary",
    "implementation_paths",
    "test_ids",
    "evidence_ids",
    "open_decision_ids",
    "evolution_ids",
}


class DetailedRequirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requirements = [
            json.loads(line)
            for line in (ROOT / "plans/_traceability/requirements.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        cls.issues = {
            item["local_id"]: item
            for item in (
                json.loads(line)
                for line in (ROOT / "jira/indexes/issues.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
        }
        cls.sections = json.loads(
            (ROOT / "plans/_indexes/plan_section_index.json").read_text(encoding="utf-8")
        )
        cls.evidence = {
            item["evidence_id"]
            for item in (
                json.loads(line)
                for line in (ROOT / "evidence/EVIDENCE_LEDGER.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
        }
        cls.tests = {
            item["test_id"]
            for item in json.loads((ROOT / "tests/TEST_CATALOG.json").read_text(encoding="utf-8"))[
                "tests"
            ]
        }

    def test_atomic_catalog_has_stable_ids_fields_and_all_domains(self) -> None:
        self.assertGreaterEqual(len(self.requirements), 352)
        identifiers = [item["requirement_id"] for item in self.requirements]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual({item["domain"] for item in self.requirements}, DOMAINS)
        for item in self.requirements:
            self.assertRegex(item["requirement_id"], REQUIREMENT_ID)
            self.assertEqual(REQUIRED_FIELDS - item.keys(), set(), item["requirement_id"])
            self.assertEqual(item["schema_version"], "2.0.0")
            self.assertIn(item["priority"], {"P0", "P1", "P2", "P3"})
            self.assertIn(item["risk"], {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
            self.assertTrue(item["statement"].strip())
            self.assertTrue(item["disposition_reason"].strip())
            self.assertTrue(item["source_references"])
            self.assertTrue(item["plan_ids"])
            self.assertTrue(item["plan_section_ids"])
            self.assertTrue(item["jira_ids"])

    def test_requirement_plan_jira_test_and_evidence_links_resolve(self) -> None:
        for item in self.requirements:
            for section_id in item["plan_section_ids"]:
                self.assertIn(section_id, self.sections, item["requirement_id"])
            for issue_id in item["jira_ids"]:
                self.assertIn(issue_id, self.issues, item["requirement_id"])
                self.assertIn(item["requirement_id"], self.issues[issue_id]["requirement_ids"])
            for test_id in item["test_ids"]:
                self.assertIn(test_id, self.tests, item["requirement_id"])
            for evidence_id in item["evidence_ids"]:
                self.assertIn(evidence_id, self.evidence, item["requirement_id"])
            for implementation_path in item["implementation_paths"]:
                self.assertTrue((ROOT / implementation_path).exists(), item["requirement_id"])
