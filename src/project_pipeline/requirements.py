from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from project_pipeline.io import read_jsonl
from project_pipeline.source_references import parse_source_reference


def load_requirement_catalog(root: Path) -> list[dict[str, Any]]:
    return read_jsonl(root / "plans" / "_traceability" / "requirements.jsonl")


def requirement_index(root: Path) -> dict[str, dict[str, Any]]:
    return {item["requirement_id"]: item for item in load_requirement_catalog(root)}


def find_requirements(
    root: Path,
    *,
    domain: str | None = None,
    implementation_state: str | None = None,
    disposition: str | None = None,
    priority: str | None = None,
    source_id: str | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    query = text.casefold() if text else None
    for item in load_requirement_catalog(root):
        if domain and item.get("domain") != domain.upper():
            continue
        if implementation_state and item.get("implementation_state") != implementation_state:
            continue
        if disposition and item.get("disposition") != disposition:
            continue
        if priority and item.get("priority") != priority.upper():
            continue
        if source_id:
            sources = {
                parse_source_reference(value).source_id
                for value in item.get("source_references", [])
            }
            if source_id.upper() not in sources:
                continue
        if query:
            searchable = " ".join(
                str(item.get(field, ""))
                for field in ("requirement_id", "title", "statement", "rationale")
            ).casefold()
            searchable += " " + " ".join(item.get("tags", [])).casefold()
            if query not in searchable:
                continue
        result.append(item)
    return sorted(result, key=lambda item: item["requirement_id"])


def summarize_requirements(requirements: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(requirements)
    counters = {
        "by_domain": Counter(item.get("domain", "UNKNOWN") for item in rows),
        "by_priority": Counter(item.get("priority", "UNKNOWN") for item in rows),
        "by_type": Counter(item.get("requirement_type", "UNKNOWN") for item in rows),
        "by_disposition": Counter(item.get("disposition", "UNKNOWN") for item in rows),
        "by_implementation_state": Counter(
            item.get("implementation_state", "UNKNOWN") for item in rows
        ),
        "by_authority": Counter(item.get("authority_classification", "UNKNOWN") for item in rows),
    }
    return {
        "schema_version": "1.0.0",
        "requirement_count": len(rows),
        **{name: dict(sorted(counter.items())) for name, counter in counters.items()},
    }
