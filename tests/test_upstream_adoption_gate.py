from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.upstream import (
    IMPLEMENTED_USAGE_STATES,
    load_upstream_registry,
    load_upstream_usage,
    validate_upstream_reviews,
)

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_has_terminal_disposition_for_every_supplied_repository() -> None:
    registry = load_upstream_registry(ROOT)
    entries = registry["entries"]
    assert registry["catalog_review_complete"] is True
    assert registry["terminal_disposition_count"] == 116
    assert len(entries) == 116
    assert all(item["disposition"] != "EVALUATE_LATER" for item in entries)
    assert all(item["catalog_review_state"] == "TERMINAL_DISPOSITION_RECORDED" for item in entries)


def test_terminal_catalog_ledger_covers_registry_exactly() -> None:
    registry_ids = {item["upstream_id"] for item in load_upstream_registry(ROOT)["entries"]}
    rows = [
        json.loads(line)
        for line in (ROOT / "provenance/catalog_dispositions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(rows) == 116
    assert {row["upstream_id"] for row in rows} == registry_ids
    assert all(row["disposition"] != "EVALUATE_LATER" for row in rows)


def test_selected_is_never_equated_with_integrated() -> None:
    usage = load_upstream_usage(ROOT)
    for record in usage:
        implemented = record["usage_state"] in IMPLEMENTED_USAGE_STATES
        paths = record.get("integration_paths", [])
        if implemented:
            assert paths, record["upstream_id"]
        else:
            assert not paths, record["upstream_id"]


def test_unresolved_license_blocks_activation() -> None:
    for item in load_upstream_registry(ROOT)["entries"]:
        if item["license"] in {
            "LICENSE_NOT_RESOLVED",
            "LICENSE_FILE_PRESENT_UNRESOLVED",
            "UNKNOWN_NOT_INSPECTED",
        }:
            assert item["dependency_activation_eligible"] is False, item["upstream_id"]
            assert item["incorporation_allowed"] is False, item["upstream_id"]


def test_subsystem_gate_has_known_candidates_and_review_state() -> None:
    gate = json.loads((ROOT / "provenance/upstream_adoption_gate.json").read_text(encoding="utf-8"))
    known = {item["upstream_id"] for item in load_upstream_registry(ROOT)["entries"]}
    assert gate["catalog_review_complete"] is True
    assert gate["subsystem_review_required_before_implementation"] is True
    assert gate["subsystems"]
    for name, record in gate["subsystems"].items():
        assert record["candidate_upstream_ids"], name
        assert set(record["candidate_upstream_ids"]) <= known
        assert record["review_state"] in {
            "CATALOG_CONSIDERED",
            "FOCUSED_REVIEW_COMPLETE",
            "INTEGRATED",
        }


def test_adoption_queue_is_closed_over_catalog_ids() -> None:
    queue = json.loads((ROOT / "provenance/adoption_queue.json").read_text(encoding="utf-8"))
    known = {item["upstream_id"] for item in load_upstream_registry(ROOT)["entries"]}
    queued: set[str] = set()
    for priority in queue["priorities"]:
        ids = set(priority["upstream_ids"])
        assert ids <= known
        queued |= ids
    assert {
        item["upstream_id"]
        for item in load_upstream_registry(ROOT)["entries"]
        if item["disposition"]
        in {
            "ADOPT_DEPENDENCY",
            "ADAPT_COMPONENT",
            "MINE_ARCHITECTURE",
            "MINE_IMPLEMENTATION_PATTERN",
            "MINE_TEST_PATTERN",
            "REJECT",
            "NOT_RELEVANT",
        }
    } <= queued | {
        # Existing concrete integrations and selected technologies already have usage records and are not required to repeat in implementation queue cohorts.
        record["upstream_id"]
        for record in load_upstream_usage(ROOT)
        if record["usage_state"] in IMPLEMENTED_USAGE_STATES
    }


def test_upstream_review_validator_enforces_gate() -> None:
    assert validate_upstream_reviews(ROOT) == []
