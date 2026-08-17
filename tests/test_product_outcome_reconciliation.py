from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductOutcomeReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.product_outcome = json.loads(
            (ROOT / "config/product_outcome.json").read_text(encoding="utf-8")
        )
        self.schema = json.loads(
            (ROOT / "schemas/product_outcome.schema.json").read_text(encoding="utf-8")
        )

    def test_product_outcome_preserves_pursuing_goal_and_src_anchors(self) -> None:
        self.assertEqual(self.product_outcome["contract_id"], "PRODUCT-OUTCOME-001")
        self.assertTrue(self.product_outcome["pursuing_goal"].strip())
        source_ids = {item["source_id"] for item in self.product_outcome["source_outcomes"]}
        self.assertTrue({"SRC-014", "SRC-015"}.issubset(source_ids))

    def test_completion_stages_are_ordered_and_non_competing(self) -> None:
        precedence = self.product_outcome["completion_stage_precedence"]
        self.assertTrue(precedence["deduplication_intent"].strip())
        self.assertTrue(precedence["non_competition_rule"].strip())

        stages = precedence["stages"]
        orders = [stage["order"] for stage in stages]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(orders, [1, 2])

        stage_ids = [stage["stage_id"] for stage in stages]
        requirement_ids = [req for stage in stages for req in stage["requirement_ids"]]
        epic_ids = [epic for stage in stages for epic in stage["jira_epic_ids"]]
        story_ids = [story for stage in stages for story in stage["jira_story_ids"]]

        self.assertEqual(len(stage_ids), len(set(stage_ids)))
        self.assertEqual(len(requirement_ids), len(set(requirement_ids)))
        self.assertEqual(len(epic_ids), len(set(epic_ids)))
        self.assertEqual(len(story_ids), len(set(story_ids)))
        self.assertIn("REQ-ASSURE-0004", requirement_ids)
        self.assertIn("REQ-REL-0003", requirement_ids)
        self.assertIn("PP-EPIC-000017", epic_ids)
        self.assertIn("PP-EPIC-000035", epic_ids)
        self.assertIn("PP-STORY-000018", story_ids)
        self.assertIn("PP-STORY-000036", story_ids)

    def test_schema_declares_required_reconciliation_fields(self) -> None:
        required = set(self.schema["required"])
        self.assertIn("contract_id", required)
        self.assertIn("pursuing_goal", required)
        self.assertIn("source_outcomes", required)
        self.assertIn("completion_stage_precedence", required)

        stage_required = set(self.schema["$defs"]["completionStage"]["required"])
        self.assertIn("requirement_ids", stage_required)
        self.assertIn("jira_epic_ids", stage_required)
        self.assertIn("jira_story_ids", stage_required)
        self.assertIn("order", stage_required)


if __name__ == "__main__":
    unittest.main()
