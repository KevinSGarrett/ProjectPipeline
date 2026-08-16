from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from project_pipeline.upstream import (
    find_upstreams,
    summarize_upstreams,
    validate_upstream_reviews,
)

ROOT = Path(__file__).resolve().parents[1]


class UpstreamReviewTests(unittest.TestCase):
    def test_reviewed_records_are_revision_pinned_and_complete(self) -> None:
        registry = json.loads(
            (ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8")
        )
        reviewed = [
            item
            for item in registry["entries"]
            if item["inspection_state"]
            in {"DEEPLY_REVIEWED", "FOCUSED_REVIEW_COMPLETE", "SOURCE_LEVEL_REVIEW_COMPLETE"}
        ]
        self.assertEqual(registry["deep_review_count"], len(reviewed))
        self.assertGreaterEqual(len(reviewed), 20)
        for item in reviewed:
            self.assertRegex(
                item["inspected_revision"],
                re.compile(
                    r"^(?:[0-9a-f]{40}|[A-Za-z0-9._/-]+@metadata(?:-snapshot)?-[0-9T:+-]+Z?)$"
                ),
            )
            self.assertTrue((ROOT / item["review_artifact"]).exists())
            self.assertTrue(item["security_concerns"])
            self.assertTrue(item["maintenance_concerns"])

    def test_dependency_activation_is_separate_from_source_incorporation(self) -> None:
        registry = json.loads(
            (ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8")
        )
        adopted = [
            item
            for item in registry["entries"]
            if item["disposition"] in {"ADOPT_DEPENDENCY", "ADAPT_COMPONENT"}
        ]
        self.assertEqual(registry["adoption_count"], len(adopted))
        self.assertGreater(len(adopted), 0)
        qualified = [
            item
            for item in adopted
            if item["inspection_state"] in {"DEEPLY_REVIEWED", "FOCUSED_REVIEW_COMPLETE"}
        ]
        self.assertTrue(all(item["dependency_activation_eligible"] for item in qualified))
        pending = [
            item
            for item in adopted
            if item["inspection_state"] not in {"DEEPLY_REVIEWED", "FOCUSED_REVIEW_COMPLETE"}
        ]
        self.assertTrue(all(not item["dependency_activation_eligible"] for item in pending))
        approved = [item for item in registry["entries"] if item.get("incorporation_allowed")]
        self.assertGreaterEqual(len(approved), 2)
        self.assertTrue(
            all(item.get("source_incorporation_state") == "APPROVED_BOUNDED" for item in approved)
        )

    def test_every_entry_has_disposition_and_bounded_copies_have_reviews(self) -> None:
        registry = json.loads(
            (ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8")
        )
        self.assertEqual(registry["entry_count"], 116)
        for item in registry["entries"]:
            self.assertTrue(item["disposition"])
            self.assertTrue(item["disposition_rationale"])
            if item.get("copied_source_paths"):
                self.assertTrue(item.get("incorporation_allowed"))
                self.assertTrue(
                    (
                        ROOT
                        / "provenance/source_incorporation_reviews"
                        / f"{item['upstream_id']}.json"
                    ).exists()
                )

    def test_upstream_queries_and_summaries_are_current(self) -> None:
        summary = summarize_upstreams(ROOT)
        observed = json.loads(
            (ROOT / "provenance/upstream_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(observed, summary)
        self.assertEqual(
            find_upstreams(ROOT, repository="hatchet-dev/hatchet"),
            find_upstreams(ROOT, upstream_id="UPSTREAM-050"),
        )
        self.assertEqual([], validate_upstream_reviews(ROOT))

    def test_review_program_covers_completed_records_and_queued_priorities(self) -> None:
        registry = json.loads(
            (ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8")
        )
        program = json.loads((ROOT / "provenance/review_program.json").read_text(encoding="utf-8"))
        reviewed = {
            item["upstream_id"]
            for item in registry["entries"]
            if item["inspection_state"]
            in {"DEEPLY_REVIEWED", "FOCUSED_REVIEW_COMPLETE", "SOURCE_LEVEL_REVIEW_COMPLETE"}
        }
        self.assertEqual(set(program["completed_review_ids"]), reviewed)
        queued = [item for item in program["review_cohorts"] if item["state"] == "QUEUED"]
        self.assertGreaterEqual(len(queued), 1)
        self.assertTrue(all(item["upstream_ids"] for item in queued))
        p0 = next(
            item
            for item in program["review_cohorts"]
            if item["cohort_id"] == "COHORT-IMPLEMENTATION-CONVERGENCE-P0"
        )
        self.assertEqual(p0["state"], "COMPLETE")
        self.assertTrue(p0.get("completion_evidence"))

    def test_review_batch_and_policy_are_current(self) -> None:
        registry = json.loads(
            (ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8")
        )
        policy = json.loads((ROOT / "provenance/license_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["entry_count"], 116)
        self.assertIn("MIT", policy["automatic_approval_spdx"])
        self.assertIn("NOASSERTION", policy["review_required_spdx"])

    def test_selected_runtime_and_license_blocked_candidates_are_distinct(self) -> None:
        registry = json.loads(
            (ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8")
        )
        index = {item["upstream_id"]: item for item in registry["entries"]}
        self.assertEqual(index["UPSTREAM-050"]["disposition"], "ADOPT_DEPENDENCY")
        self.assertTrue(index["UPSTREAM-050"]["dependency_activation_eligible"])
        self.assertEqual(index["UPSTREAM-012"]["source_strategy"], "SOURCE_SELECTED_STABLE_PROXY")
        self.assertTrue(index["UPSTREAM-012"]["dependency_activation_eligible"])

    def test_every_catalog_entry_has_an_explicit_rationale(self) -> None:
        registry = json.loads(
            (ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8")
        )
        self.assertTrue(
            all(
                item.get("disposition") and item.get("disposition_rationale")
                for item in registry["entries"]
            )
        )
