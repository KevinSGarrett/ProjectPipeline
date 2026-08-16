from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl


def load_source_sections(root: Path) -> list[dict[str, Any]]:
    return read_jsonl(root / "plans" / "_traceability" / "source_sections.jsonl")


def source_section_summary(root: Path) -> dict[str, Any]:
    rows = load_source_sections(root)
    by_source = Counter(row["source_id"] for row in rows)
    by_disposition = Counter(row["disposition"] for row in rows)
    linked = sum(bool(row.get("requirement_ids")) for row in rows)
    explicit = sum(bool(row.get("disposition_reason")) for row in rows)
    return {
        "schema_version": "1.0.0",
        "section_count": len(rows),
        "linked_requirement_section_count": linked,
        "explicit_disposition_count": explicit,
        "by_source": dict(sorted(by_source.items())),
        "by_disposition": dict(sorted(by_disposition.items())),
    }


def validate_source_section_summary(root: Path) -> list[str]:
    path = root / "plans" / "_traceability" / "source_section_summary.json"
    if not path.exists():
        return ["Source-section summary is missing"]
    expected = source_section_summary(root)
    observed = read_json(path)
    return [] if observed == expected else ["Source-section summary is stale"]
