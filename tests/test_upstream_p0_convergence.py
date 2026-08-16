from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.upstream import (
    IMPLEMENTED_USAGE_STATES,
    load_p0_convergence,
    load_upstream_usage,
    validate_upstream_reviews,
)

ROOT = Path(__file__).resolve().parents[1]
P0_IDS = {
    "UPSTREAM-011",
    "UPSTREAM-041",
    "UPSTREAM-043",
    "UPSTREAM-045",
    "UPSTREAM-047",
    "UPSTREAM-073",
    "UPSTREAM-085",
    "UPSTREAM-094",
    "UPSTREAM-102",
    "UPSTREAM-108",
    "UPSTREAM-115",
    "UPSTREAM-116",
}


def test_p0_convergence_exactly_covers_priority_queue():
    queue = json.loads((ROOT / "provenance/adoption_queue.json").read_text(encoding="utf-8"))
    queued = set()
    for priority in queue["priorities"]:
        if priority["priority"] == "P0":
            queued.update(priority["upstream_ids"])
    report = load_p0_convergence(ROOT)
    assert queued == P0_IDS == {row["upstream_id"] for row in report["records"]}
    assert report["status"] == "PASS"
    assert report["pass_12_upstream_prerequisite_satisfied"] is True


def test_every_p0_record_has_real_integration_and_tests():
    report = load_p0_convergence(ROOT)
    for row in report["records"]:
        assert row["convergence_outcome"] == "IMPLEMENTED_ADAPTER"
        assert row["integration_paths"]
        assert row["test_paths"]
        for relative in [*row["integration_paths"], *row["test_paths"]]:
            assert (ROOT / relative).is_file(), relative
        assert row["live_qualification"] == "NOT_LIVE_VERIFIED"
        assert row["source_incorporated"] is False


def test_p0_usage_states_are_implemented_not_selection_placeholders():
    usage = {row["upstream_id"]: row for row in load_upstream_usage(ROOT)}
    for upstream_id in P0_IDS:
        assert usage[upstream_id]["usage_state"] in IMPLEMENTED_USAGE_STATES
        assert usage[upstream_id]["integration_paths"]
        assert usage[upstream_id]["activation_eligible"] is True


def test_p0_reviews_are_source_level_and_licenses_resolved():
    registry = json.loads((ROOT / "provenance/upstream_registry.json").read_text(encoding="utf-8"))
    index = {row["upstream_id"]: row for row in registry["entries"]}
    for upstream_id in P0_IDS:
        row = index[upstream_id]
        assert row["inspection_state"] in {
            "SOURCE_LEVEL_REVIEW_COMPLETE",
            "FOCUSED_REVIEW_COMPLETE",
            "DEEPLY_REVIEWED",
        }
        assert row["license"] not in {
            "UNKNOWN_NOT_INSPECTED",
            "LICENSE_FILE_PRESENT_UNRESOLVED",
            "LICENSE_NOT_RESOLVED",
        }
        assert row["review_artifact"]
        assert (ROOT / row["review_artifact"]).is_file()


def test_permanent_upstream_validator_accepts_p0_convergence():
    assert validate_upstream_reviews(ROOT) == []
