from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, read_jsonl
from project_pipeline.requirements import load_requirement_catalog, summarize_requirements


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def render_glossary(root: Path) -> str:
    glossary = read_json(root / "plans" / "01_requirements" / "glossary.json")
    lines = ["# Project Pipeline Glossary", "", f"Terms: `{glossary['term_count']}`", ""]
    for term, entry in sorted(glossary["terms"].items()):
        display = term.replace("_", " ").title()
        lines.extend([f"## {display}", "", entry["definition"], ""])
        aliases = entry.get("aliases", [])
        if aliases:
            lines.append("Aliases: " + ", ".join(f"`{value}`" for value in aliases))
        lines.append("Sources: " + ", ".join(f"`{value}`" for value in entry["source_references"]))
        lines.append("")
    return "\n".join(lines)


def render_open_decisions(root: Path) -> str:
    decisions = read_jsonl(root / "plans" / "01_requirements" / "open_decisions.jsonl")
    lines = ["# Open Decision Register", "", f"Decisions: `{len(decisions)}`", ""]
    for item in decisions:
        lines.extend(
            [
                f"## {item['decision_id']} — {item['topic']}",
                "",
                f"**Status:** `{item['status']}`",
                "",
                *(
                    [
                        "**Resolved by:** "
                        + ", ".join(
                            f"`{value}`" for value in item.get("resolved_by_decision_ids", [])
                        ),
                        "",
                        f"**Resolution:** {item.get('resolution')}",
                        "",
                    ]
                    if item.get("status") == "RESOLVED"
                    else []
                ),
                item["question"],
                "",
                "**Options**",
                "",
            ]
        )
        lines.extend(f"- {value}" for value in item["options"])
        lines.extend(["", "**Constraints**", ""])
        lines.extend(f"- {value}" for value in item["constraints"])
        lines.extend(
            [
                "",
                f"**Resolution method:** {item['resolution_method']}",
                "",
                f"**Decision gate:** {item['decision_gate']}",
                "",
                "**Required by plans:** "
                + ", ".join(f"`{value}`" for value in item["required_by_plan_ids"]),
                "",
                "**Linked requirements:** "
                + ", ".join(f"`{value}`" for value in item["linked_requirement_ids"]),
                "",
                "**Sources:** " + ", ".join(f"`{value}`" for value in item["source_references"]),
                "",
            ]
        )
    return "\n".join(lines)


def render_source_evolution(root: Path) -> str:
    records = read_jsonl(root / "plans" / "01_requirements" / "source_evolution.jsonl")
    lines = ["# Source Evolution Register", "", f"Records: `{len(records)}`", ""]
    for item in records:
        lines.extend(
            [
                f"## {item['record_id']} — {item['relationship'].replace('_', ' ').title()}",
                "",
                f"**Sources:** {', '.join(f'`{value}`' for value in item['source_ids'])}",
                "",
                f"**Handling:** {item['handling']}",
                "",
                f"**Requirement effect:** {item['requirement_effect']}",
                "",
                "**Linked requirements:** "
                + ", ".join(f"`{value}`" for value in item["linked_requirement_ids"]),
                "",
            ]
        )
        earlier = item.get("earlier_references", [])
        later = item.get("later_references", [])
        if earlier:
            lines.extend(["Earlier ranges: " + ", ".join(f"`{value}`" for value in earlier), ""])
        if later:
            lines.extend(["Later ranges: " + ", ".join(f"`{value}`" for value in later), ""])
    return "\n".join(lines)


def render_catalog_status(root: Path) -> str:
    requirements = load_requirement_catalog(root)
    summary = summarize_requirements(requirements)
    section_summary = read_json(root / "plans" / "_traceability" / "source_section_summary.json")
    lines = [
        "# Requirement Catalog Status",
        "",
        f"- Requirements: `{summary['requirement_count']}`",
        f"- Domains: `{len(summary['by_domain'])}`",
        f"- Canonical source sections: `{section_summary['section_count']}`",
        f"- Source sections with explicit dispositions: `{section_summary['explicit_disposition_count']}`",
        "",
        "## Implementation state",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in summary["by_implementation_state"].items())
    lines.extend(["", "## Priority", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in summary["by_priority"].items())
    lines.extend(["", "## Domain", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in summary["by_domain"].items())
    lines.extend(
        [
            "",
            "## Retrieval",
            "",
            "Use `PYTHONPATH=src python -m project_pipeline requirements --root . --summary` for the complete summary.",
            "Use focused filters such as `--id`, `--domain`, `--source`, `--priority`, `--state`, and `--text` to retrieve bounded context.",
        ]
    )
    return "\n".join(lines)


def expected_views(root: Path) -> dict[Path, str]:
    base = root / "plans" / "01_requirements"
    return {
        base / "GLOSSARY.md": render_glossary(root),
        base / "OPEN_DECISIONS.md": render_open_decisions(root),
        base / "SOURCE_EVOLUTION.md": render_source_evolution(root),
        base / "REQUIREMENT_CATALOG_STATUS.md": render_catalog_status(root),
    }


def write_requirement_views(root: Path) -> dict[str, Any]:
    views = expected_views(root)
    for path, content in views.items():
        _write(path, content)
    return {
        "view_count": len(views),
        "paths": sorted(path.relative_to(root).as_posix() for path in views),
    }


def validate_requirement_views(root: Path) -> list[str]:
    errors: list[str] = []
    for path, content in expected_views(root).items():
        expected = content.rstrip() + "\n"
        if not path.exists():
            errors.append(
                f"Generated requirement view is missing: {path.relative_to(root).as_posix()}"
            )
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(
                f"Generated requirement view is stale: {path.relative_to(root).as_posix()}"
            )
    return errors
