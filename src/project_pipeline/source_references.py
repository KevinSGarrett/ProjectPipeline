from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_pipeline.ids import SOURCE_REFERENCE
from project_pipeline.io import read_json


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_id: str
    start_line: int
    end_line: int

    @property
    def citation(self) -> str:
        if self.start_line == self.end_line:
            return f"{self.source_id}:L{self.start_line:06d}"
        return f"{self.source_id}:L{self.start_line:06d}-L{self.end_line:06d}"


def parse_source_reference(value: str) -> SourceReference:
    if not SOURCE_REFERENCE.fullmatch(value):
        raise ValueError(f"Invalid source reference: {value}")
    source_id, lines = value.split(":", 1)
    parts = lines.split("-")
    start = int(parts[0][1:])
    end = int(parts[1][1:]) if len(parts) == 2 else start
    if start < 1 or end < start:
        raise ValueError(f"Invalid source line range: {value}")
    return SourceReference(source_id=source_id, start_line=start, end_line=end)


def load_source_metadata(root: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(root / "provenance" / "source_registry.json")
    metadata = {item["source_id"]: dict(item) for item in registry["sources"]}
    comparison = read_json(root / "provenance" / "governing_prompt_comparison.json")
    governing_line_count = max(
        int(comparison["input_a"]["line_count"]),
        int(comparison["input_b"]["line_count"]),
    )
    metadata["GOV-001"] = {
        "source_id": "GOV-001",
        "line_count": governing_line_count,
        "sequence": 0,
        "title": "Project Pipeline governing execution contract",
        "exact_duplicate_of": None,
        "exact_prefix_of": None,
    }
    return metadata


def validate_source_reference(root: Path, value: str) -> list[str]:
    try:
        reference = parse_source_reference(value)
    except ValueError as error:
        return [str(error)]
    metadata = load_source_metadata(root)
    source = metadata.get(reference.source_id)
    if source is None:
        return [f"Unknown source identifier: {reference.source_id}"]
    line_count = int(source["line_count"])
    if reference.end_line > line_count:
        return [f"Source range exceeds {reference.source_id} line count {line_count}: {value}"]
    return []


def canonical_evidence_key(root: Path, value: str) -> tuple[str, int, int]:
    """Return a duplicate-aware key for evidentiary counting.

    Exact duplicates and exact-prefix aliases collapse to the later canonical source so
    the same text is not treated as independent confirmation.
    """

    reference = parse_source_reference(value)
    metadata = load_source_metadata(root)
    source = metadata[reference.source_id]
    canonical = source.get("exact_duplicate_of") or source.get("exact_prefix_of")
    source_id = str(canonical or reference.source_id)
    return source_id, reference.start_line, reference.end_line


def references_overlap(left: SourceReference, right: SourceReference) -> bool:
    return (
        left.source_id == right.source_id
        and left.start_line <= right.end_line
        and right.start_line <= left.end_line
    )
