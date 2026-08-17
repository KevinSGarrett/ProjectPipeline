from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.validation.pp380_dispositions import (
    validate_pp380_corrected_dispositions,
)

ROOT = Path(__file__).resolve().parents[1]


def test_corrected_pp380_dispositions_are_hash_verified_and_complete() -> None:
    report_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    errors = validate_pp380_corrected_dispositions(ROOT, report_path)
    assert errors == []


def test_corrected_pp380_dispositions_tampered_receipt_fails(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document["generation_proof"]["verification_receipt_sha256"] = "0" * 64
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered)
    assert "generation_proof verification receipt is invalid" in errors


def test_corrected_pp380_dispositions_runtime_evidence_regeneration_fails(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    row = next(
        entry
        for entry in document["rows"]
        if entry["original_category"] == "LOCAL_RUNTIME_EVIDENCE"
    )
    row["proposed_final_action"] = "REGENERATE_AFTER_INTEGRATION"
    tampered = tmp_path / "tampered_runtime.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered)
    assert any("runtime evidence must preserve observed artifact" in error for error in errors)


def test_corrected_pp380_dispositions_unknown_owner_regeneration_fails(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    row = next(entry for entry in document["rows"] if entry["original_category"] == "UNKNOWN_OWNER")
    row["proposed_final_action"] = "REGENERATE_AFTER_INTEGRATION"
    tampered = tmp_path / "tampered_owner.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered)
    assert any(
        "unknown owner row must remain preserved pending attestation" in error for error in errors
    )
