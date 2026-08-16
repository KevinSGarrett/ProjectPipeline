from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProvenanceTests(unittest.TestCase):
    def test_knowledge_pack_registry_preserves_source_relations(self) -> None:
        registry = json.loads(
            (ROOT / "provenance" / "source_registry.json").read_text(encoding="utf-8")
        )
        pack = json.loads(
            (ROOT / "provenance" / "source_pack_reference.json").read_text(encoding="utf-8")
        )
        self.assertEqual(registry["source_count"], 18)
        self.assertEqual(len(pack["exact_duplicates"]), 1)
        self.assertEqual(len(pack["exact_prefix_relations"]), 1)
        self.assertEqual(pack["independent_validation_result"], "PASS")

    def test_governing_prompt_aliases_are_reconciled_without_hiding_raw_hashes(self) -> None:
        comparison = json.loads(
            (ROOT / "provenance" / "governing_prompt_comparison.json").read_text(encoding="utf-8")
        )
        self.assertNotEqual(comparison["input_a"]["sha256"], comparison["input_b"]["sha256"])
        self.assertEqual(
            comparison["comparison_result"], "SUBSTANTIVELY_EQUIVALENT_AFTER_MARKDOWN_NORMALIZATION"
        )

    def test_upstream_catalog_is_unique_and_governed(self) -> None:
        registry = json.loads(
            (ROOT / "provenance" / "upstream_registry.json").read_text(encoding="utf-8")
        )
        urls = [entry["canonical_url"] for entry in registry["entries"]]
        self.assertEqual(registry["entry_count"], 116)
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(registry["invalid_url_count"], 0)
        self.assertIn("ADOPT_DEPENDENCY", {entry["disposition"] for entry in registry["entries"]})
        approved = [entry for entry in registry["entries"] if entry.get("incorporation_allowed")]
        self.assertGreaterEqual(len(approved), 2)
        for entry in approved:
            self.assertEqual(entry.get("source_incorporation_state"), "APPROVED_BOUNDED")
            review = (
                ROOT
                / "provenance"
                / "source_incorporation_reviews"
                / f"{entry['upstream_id']}.json"
            )
            self.assertTrue(review.exists(), entry["upstream_id"])
            self.assertTrue(entry.get("copied_source_paths"), entry["upstream_id"])
        self.assertTrue(all(entry["disposition_rationale"] for entry in registry["entries"]))
