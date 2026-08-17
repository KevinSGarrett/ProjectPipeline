from __future__ import annotations

from pathlib import Path

from project_pipeline.validation.pp380_dispositions import (
    validate_pp380_corrected_dispositions,
)

ROOT = Path(__file__).resolve().parents[1]


def test_corrected_pp380_dispositions_are_hash_verified_and_complete() -> None:
    report_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    errors = validate_pp380_corrected_dispositions(ROOT, report_path)
    assert errors == []
