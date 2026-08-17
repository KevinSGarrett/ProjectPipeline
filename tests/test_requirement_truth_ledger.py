from __future__ import annotations

from pathlib import Path

from project_pipeline.assurance.requirement_truth_ledger import (
    build_requirement_truth_ledger,
    validate_requirement_truth_ledger,
)

ROOT = Path(__file__).resolve().parents[1]


def test_requirement_truth_ledger_has_exactly_352_valid_rows() -> None:
    document = build_requirement_truth_ledger(ROOT)
    assert document["row_count"] == 352
    assert len({row["requirement_id"] for row in document["rows"]}) == 352
    assert validate_requirement_truth_ledger(document, ROOT) == []
    implemented = [row for row in document["rows"] if row["disposition"] == "IMPLEMENTED_VERIFIED"]
    assert implemented
    assert all(row["evidence"] for row in implemented)


def test_requirement_truth_ledger_rejects_duplicate_missing_and_hash_drift() -> None:
    document = build_requirement_truth_ledger(ROOT)
    first = dict(document["rows"][0])
    document["rows"].append(first)
    document["rows"][1]["canonical_source_hash"] = "0" * 64
    document["rows"][2]["requirement_id"] = "REQ-NOT-REAL-0001"
    document["rows"][3]["disposition"] = "IMPLEMENTED_VERIFIED"
    document["rows"][3]["evidence"] = []
    errors = validate_requirement_truth_ledger(document, ROOT)
    assert any("duplicate requirement_id" in error for error in errors)
    assert any("hash drift" in error for error in errors)
    assert any("unknown requirement_id" in error for error in errors)
    assert any("implemented requirement lacks evidence" in error for error in errors)
