from __future__ import annotations

import json
import unittest
from collections import defaultdict
from pathlib import Path

from project_pipeline.section_coverage import validate_source_section_summary
from project_pipeline.source_references import parse_source_reference, validate_source_reference

ROOT = Path(__file__).resolve().parents[1]


class SourceSectionCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = [
            json.loads(line)
            for line in (ROOT / "plans/_traceability/source_sections.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        cls.requirements = {
            item["requirement_id"]: item
            for item in (
                json.loads(line)
                for line in (ROOT / "plans/_traceability/requirements.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
        }

    def test_every_canonical_section_has_one_explicit_disposition(self) -> None:
        expected = json.loads(
            (ROOT / "provenance/source_pack_reference.json").read_text(encoding="utf-8")
        )["statistics"]["section_count"]
        self.assertEqual(len(self.rows), expected)
        self.assertEqual(len({row["section_id"] for row in self.rows}), expected)
        by_source: dict[str, list[int]] = defaultdict(list)
        for row in self.rows:
            by_source[row["source_id"]].append(row["ordinal"])
            self.assertTrue(row["disposition"])
            self.assertTrue(row["disposition_reason"].strip())
            self.assertEqual(validate_source_reference(ROOT, row["source_reference"]), [])
            parsed = parse_source_reference(row["source_reference"])
            self.assertEqual(
                (parsed.start_line, parsed.end_line), (row["start_line"], row["end_line"])
            )
            self.assertRegex(row["content_sha256"], r"^[0-9a-f]{64}$")
        for ordinals in by_source.values():
            self.assertEqual(sorted(ordinals), list(range(1, len(ordinals) + 1)))

    def test_duplicate_and_prefix_sources_are_not_independent_confirmation(self) -> None:
        src18 = [row for row in self.rows if row["source_id"] == "SRC-018"]
        src5 = [row for row in self.rows if row["source_id"] == "SRC-005"]
        self.assertTrue(src18 and src5)
        self.assertEqual({row["disposition"] for row in src18}, {"DUPLICATE_SOURCE"})
        self.assertEqual({row["disposition"] for row in src5}, {"PREFIX_OVERLAP_SOURCE"})

    def test_linked_sections_overlap_their_requirements_and_summary_is_current(self) -> None:
        for row in self.rows:
            section = parse_source_reference(row["source_reference"])
            for requirement_id in row["requirement_ids"]:
                self.assertIn(requirement_id, self.requirements)
                refs = [
                    parse_source_reference(value)
                    for value in self.requirements[requirement_id]["source_references"]
                ]
                self.assertTrue(
                    any(
                        ref.source_id == section.source_id
                        and ref.start_line <= section.end_line
                        and section.start_line <= ref.end_line
                        for ref in refs
                    ),
                    (row["section_id"], requirement_id),
                )
        self.assertEqual(validate_source_section_summary(ROOT), [])
