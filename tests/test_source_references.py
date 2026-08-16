from __future__ import annotations

import json
import unittest
from pathlib import Path

from project_pipeline.source_references import (
    canonical_evidence_key,
    parse_source_reference,
    validate_source_reference,
)

ROOT = Path(__file__).resolve().parents[1]


class SourceReferenceTests(unittest.TestCase):
    def test_parse_and_validate_exact_source_ranges(self) -> None:
        reference = parse_source_reference("SRC-001:L000001-L000020")
        self.assertEqual(reference.source_id, "SRC-001")
        self.assertEqual(reference.start_line, 1)
        self.assertEqual(reference.end_line, 20)
        self.assertEqual(validate_source_reference(ROOT, reference.citation), [])
        self.assertEqual(validate_source_reference(ROOT, "GOV-001:L002350"), [])
        self.assertTrue(validate_source_reference(ROOT, "SRC-001:L001593"))

    def test_duplicate_and_prefix_sources_share_evidence_identity(self) -> None:
        self.assertEqual(
            canonical_evidence_key(ROOT, "SRC-017:L000009-L000071"),
            canonical_evidence_key(ROOT, "SRC-018:L000009-L000071"),
        )
        self.assertEqual(
            canonical_evidence_key(ROOT, "SRC-005:L000057-L000129"),
            canonical_evidence_key(ROOT, "SRC-006:L000057-L000129"),
        )

    def test_requirement_source_ranges_are_valid_and_duplicate_aware(self) -> None:
        path = ROOT / "plans" / "_traceability" / "requirements.jsonl"
        requirements = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for item in requirements:
            keys = []
            for value in item["source_references"]:
                self.assertEqual(validate_source_reference(ROOT, value), [], item["requirement_id"])
                keys.append(canonical_evidence_key(ROOT, value))
            self.assertEqual(len(keys), len(set(keys)), item["requirement_id"])
