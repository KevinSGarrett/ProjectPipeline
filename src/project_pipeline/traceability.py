from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, write_json, write_jsonl
from project_pipeline.requirements import load_requirement_catalog, summarize_requirements
from project_pipeline.source_references import parse_source_reference


def load_requirements(root: Path) -> list[dict[str, Any]]:
    return load_requirement_catalog(root)


def coverage_summary(root: Path) -> dict[str, Any]:
    requirements = load_requirements(root)
    by_state = Counter(item["implementation_state"] for item in requirements)
    by_disposition = Counter(item["disposition"] for item in requirements)
    by_domain = Counter(item.get("domain", "UNKNOWN") for item in requirements)
    by_priority = Counter(item.get("priority", "UNKNOWN") for item in requirements)
    by_type = Counter(item.get("requirement_type", "UNKNOWN") for item in requirements)
    by_authority = Counter(item.get("authority_classification", "UNKNOWN") for item in requirements)
    mappings = {
        "plan": sum(bool(item.get("plan_ids")) for item in requirements),
        "jira": sum(bool(item.get("jira_ids")) for item in requirements),
        "implementation": sum(bool(item.get("implementation_paths")) for item in requirements),
        "tests": sum(bool(item.get("test_ids")) for item in requirements),
        "evidence": sum(bool(item.get("evidence_ids")) for item in requirements),
    }
    source_counts: Counter[str] = Counter()
    for item in requirements:
        for value in item.get("source_references", []):
            source_counts[parse_source_reference(value).source_id] += 1
    total = len(requirements)
    unexplained: list[str] = []
    for item in requirements:
        requirement_id = item["requirement_id"]
        if not item.get("source_references"):
            unexplained.append(f"{requirement_id}: missing source reference")
        if not item.get("plan_ids"):
            unexplained.append(f"{requirement_id}: missing plan")
        if not item.get("jira_ids"):
            unexplained.append(f"{requirement_id}: missing work item")
        if not item.get("disposition_reason"):
            unexplained.append(f"{requirement_id}: missing disposition reason")
        if item["implementation_state"] in {"IMPLEMENTED", "MOCK_VERIFIED", "LIVE_VERIFIED"}:
            if not item.get("implementation_paths"):
                unexplained.append(f"{requirement_id}: implemented state lacks implementation path")
            if not item.get("test_ids"):
                unexplained.append(f"{requirement_id}: implemented state lacks test")
            if not item.get("evidence_ids"):
                unexplained.append(f"{requirement_id}: implemented state lacks evidence")
    section_summary_path = root / "plans" / "_traceability" / "source_section_summary.json"
    section_summary = read_json(section_summary_path) if section_summary_path.exists() else None
    return {
        "schema_version": "2.0.0",
        "requirement_count": total,
        "by_implementation_state": dict(sorted(by_state.items())),
        "by_disposition": dict(sorted(by_disposition.items())),
        "by_domain": dict(sorted(by_domain.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "by_requirement_type": dict(sorted(by_type.items())),
        "by_authority": dict(sorted(by_authority.items())),
        "requirements_by_source": dict(sorted(source_counts.items())),
        "mapped_counts": mappings,
        "mapped_percent": {
            key: round((value / total * 100.0), 2) if total else 100.0
            for key, value in mappings.items()
        },
        "source_section_coverage": section_summary,
        "unexplained_gap_count": len(unexplained),
        "unexplained_gaps": unexplained,
    }


def write_coverage_artifacts(root: Path) -> dict[str, Any]:
    summary = coverage_summary(root)
    target = root / "plans" / "_traceability"
    write_json(target / "coverage_report.json", summary)
    lines = [
        "# Requirement Coverage",
        "",
        f"- Requirements: `{summary['requirement_count']}`",
        f"- Unexplained gaps: `{summary['unexplained_gap_count']}`",
        "",
        "## Implementation state",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in summary["by_implementation_state"].items())
    lines.extend(["", "## Domain coverage", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in summary["by_domain"].items())
    lines.extend(["", "## Mapping coverage", ""])
    for key, value in summary["mapped_counts"].items():
        lines.append(f"- `{key}`: {value} ({summary['mapped_percent'][key]}%)")
    if summary.get("source_section_coverage"):
        section = summary["source_section_coverage"]
        lines.extend(
            [
                "",
                "## Canonical source-section disposition",
                "",
                f"- Sections: `{section['section_count']}`",
                f"- Sections linked to requirements: `{section['linked_requirement_section_count']}`",
                f"- Sections with explicit disposition: `{section['explicit_disposition_count']}`",
            ]
        )
    lines.extend(["", "## Unexplained gaps", ""])
    if summary["unexplained_gaps"]:
        lines.extend(f"- {item}" for item in summary["unexplained_gaps"])
    else:
        lines.append("None.")
    (target / "coverage_report.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def rebuild_traceability_exports(root: Path) -> None:
    requirements = load_requirements(root)
    target = root / "plans" / "_traceability"
    mappings = {
        "requirements_to_plans.jsonl": "plan_ids",
        "requirements_to_jira.jsonl": "jira_ids",
        "requirements_to_implementation.jsonl": "implementation_paths",
        "requirements_to_tests.jsonl": "test_ids",
        "requirements_to_evidence.jsonl": "evidence_ids",
        "requirements_to_decisions.jsonl": "decision_ids",
        "requirements_to_open_decisions.jsonl": "open_decision_ids",
        "requirements_to_evolution.jsonl": "evolution_ids",
    }
    for filename, field in mappings.items():
        write_jsonl(
            target / filename,
            [
                {"requirement_id": item["requirement_id"], field: item.get(field, [])}
                for item in requirements
            ],
        )
    source_to_requirements: dict[str, list[str]] = defaultdict(list)
    for item in requirements:
        for reference in item.get("source_references", []):
            source_to_requirements[reference].append(item["requirement_id"])
    write_jsonl(
        target / "source_to_requirements.jsonl",
        [
            {
                "source_reference": reference,
                "requirement_ids": sorted(requirement_ids),
            }
            for reference, requirement_ids in sorted(source_to_requirements.items())
        ],
    )

    by_id = {item["requirement_id"]: item for item in requirements}
    by_domain: dict[str, list[str]] = defaultdict(list)
    by_source: dict[str, list[str]] = defaultdict(list)
    for item in requirements:
        requirement_id = item["requirement_id"]
        by_domain[item["domain"]].append(requirement_id)
        for reference in item.get("source_references", []):
            by_source[parse_source_reference(reference).source_id].append(requirement_id)
    write_json(target / "requirements_by_id.json", by_id)
    write_json(
        target / "requirements_by_domain.json",
        {key: sorted(value) for key, value in sorted(by_domain.items())},
    )
    write_json(
        target / "requirements_by_source.json",
        {key: sorted(set(value)) for key, value in sorted(by_source.items())},
    )

    summary = summarize_requirements(requirements)
    summary["by_state"] = summary.pop("by_implementation_state")
    write_json(target / "requirement_registry_summary.json", summary)
