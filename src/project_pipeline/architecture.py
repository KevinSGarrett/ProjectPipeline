from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from project_pipeline.io import read_json, read_jsonl, write_json, write_jsonl

COMPONENT_ID = re.compile(r"^COMP-[A-Z0-9-]+-[0-9]{3}$")
TECHNOLOGY_ID = re.compile(r"^TECH-[A-Z0-9-]+-[0-9]{3}$")
BOUNDARY_ID = re.compile(r"^BOUNDARY-[A-Z0-9-]+-[0-9]{3}$")
INTERFACE_ID = re.compile(r"^IFACE-[A-Z0-9-]+-[0-9]{3}$")
FLOW_ID = re.compile(r"^FLOW-[A-Z0-9-]+-[0-9]{3}$")


def _architecture_path(root: Path, name: str) -> Path:
    return root / "architecture" / name


def load_component_catalog(root: Path) -> dict[str, Any]:
    return cast(dict[str, Any], read_json(_architecture_path(root, "component_catalog.json")))


def load_technology_stack(root: Path) -> dict[str, Any]:
    return cast(dict[str, Any], read_json(_architecture_path(root, "technology_stack.json")))


def component_index(root: Path) -> dict[str, dict[str, Any]]:
    return {
        item["component_id"]: item for item in load_component_catalog(root).get("components", [])
    }


def find_components(
    root: Path,
    *,
    component_id: str | None = None,
    layer: str | None = None,
    implementation_state: str | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    query = text.casefold() if text else None
    result: list[dict[str, Any]] = []
    for item in load_component_catalog(root).get("components", []):
        if component_id and item.get("component_id") != component_id:
            continue
        if layer and item.get("layer") != layer.upper():
            continue
        if implementation_state and item.get("implementation_state") != implementation_state:
            continue
        if query:
            searchable = " ".join(
                str(item.get(field, ""))
                for field in ("component_id", "name", "responsibility", "authority")
            ).casefold()
            searchable += " " + " ".join(item.get("tags", [])).casefold()
            if query not in searchable:
                continue
        result.append(item)
    return sorted(result, key=lambda item: item["component_id"])


def build_decision_map(root: Path) -> dict[str, Any]:
    catalog = read_json(root / "adr" / "ADR_CATALOG.json")
    components = load_component_catalog(root).get("components", [])
    technologies = load_technology_stack(root).get("technologies", [])
    by_decision_components: dict[str, set[str]] = {}
    for component in components:
        for decision_id in component.get("decision_ids", []):
            by_decision_components.setdefault(decision_id, set()).add(component["component_id"])
    by_decision_technologies: dict[str, set[str]] = {}
    for technology in technologies:
        by_decision_technologies.setdefault(technology["decision_id"], set()).add(
            technology["technology_id"]
        )
    records = []
    for decision in catalog.get("decisions", []):
        decision_id = decision["decision_id"]
        records.append(
            {
                "decision_id": decision_id,
                "title": decision["title"],
                "status": decision["status"],
                "path": decision["path"],
                "source_references": decision.get("source_references", []),
                "requirement_ids": decision.get("requirement_ids", []),
                "component_ids": sorted(
                    set(decision.get("component_ids", []))
                    | by_decision_components.get(decision_id, set())
                ),
                "technology_ids": sorted(by_decision_technologies.get(decision_id, set())),
            }
        )
    return {
        "schema_version": "1.0.0",
        "decision_count": len(records),
        "decisions": records,
    }


def summarize_architecture(root: Path) -> dict[str, Any]:
    catalog = load_component_catalog(root)
    stack = load_technology_stack(root)
    components = catalog.get("components", [])
    technologies = stack.get("technologies", [])
    return {
        "schema_version": "1.0.0",
        "component_count": len(components),
        "technology_count": len(technologies),
        "trust_boundary_count": read_json(_architecture_path(root, "trust_boundaries.json")).get(
            "boundary_count", 0
        ),
        "deployment_profile_count": len(
            read_json(_architecture_path(root, "deployment_profiles.json")).get("profiles", [])
        ),
        "by_layer": dict(sorted(Counter(item["layer"] for item in components).items())),
        "by_implementation_state": dict(
            sorted(Counter(item["implementation_state"] for item in components).items())
        ),
        "technologies_by_lifecycle": dict(
            sorted(Counter(item["lifecycle_status"] for item in technologies).items())
        ),
        "canonical_state_owner": stack.get("canonical_state_owner"),
        "durable_execution_backend": stack.get("durable_execution_backend"),
        "operator_stack": stack.get("operator_stack"),
    }


def render_architecture_summary(root: Path) -> str:
    summary = summarize_architecture(root)
    catalog = load_component_catalog(root)
    stack = load_technology_stack(root)
    lines = [
        "# Target Architecture Summary",
        "",
        f"- Components: `{summary['component_count']}`",
        f"- Technology selections and qualified alternatives: `{summary['technology_count']}`",
        f"- Trust boundaries: `{summary['trust_boundary_count']}`",
        f"- Deployment profiles: `{summary['deployment_profile_count']}`",
        f"- Canonical state owner: `{summary['canonical_state_owner']}`",
        f"- Initial durable execution backend: `{summary['durable_execution_backend']}`",
        f"- Operator stack: `{summary['operator_stack']}`",
        "",
        "## Authority model",
        "",
        catalog["authority_model"],
        "",
        "## Components by layer",
        "",
    ]
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for item in catalog["components"]:
        by_layer.setdefault(item["layer"], []).append(item)
    for layer in sorted(by_layer):
        lines.extend([f"### {layer.replace('_', ' ').title()}", ""])
        for item in sorted(by_layer[layer], key=lambda value: value["component_id"]):
            lines.append(
                f"- `{item['component_id']}` — **{item['name']}**: {item['responsibility']} "
                f"(`{item['implementation_state']}`)"
            )
        lines.append("")
    lines.extend(["## Technology decisions", ""])
    for item in stack["technologies"]:
        lines.append(
            f"- `{item['technology_id']}` — **{item['selection']}**: {item['role']} "
            f"(`{item['lifecycle_status']}`, `{item['decision_id']}`)"
        )
    lines.extend(
        [
            "",
            "## Navigation",
            "",
            "Use `PYTHONPATH=src python -m project_pipeline architecture --root . --summary` for the machine-readable summary.",
            "Use `--component`, `--layer`, `--state`, and `--text` for bounded retrieval.",
        ]
    )
    return "\n".join(lines)


def build_requirement_component_maps(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    components = load_component_catalog(root).get("components", [])
    requirement_to_components: dict[str, set[str]] = {}
    component_rows: list[dict[str, Any]] = []
    for component in components:
        requirement_ids = sorted(set(component.get("requirement_ids", [])))
        component_rows.append(
            {"component_id": component["component_id"], "requirement_ids": requirement_ids}
        )
        for requirement_id in requirement_ids:
            requirement_to_components.setdefault(requirement_id, set()).add(
                component["component_id"]
            )
    requirement_rows = [
        {"requirement_id": requirement_id, "component_ids": sorted(component_ids)}
        for requirement_id, component_ids in sorted(requirement_to_components.items())
    ]
    return requirement_rows, sorted(component_rows, key=lambda row: row["component_id"])


def write_architecture_views(root: Path) -> dict[str, Any]:
    summary = summarize_architecture(root)
    write_json(_architecture_path(root, "architecture_summary.json"), summary)
    write_json(_architecture_path(root, "decision_map.json"), build_decision_map(root))
    requirement_rows, component_rows = build_requirement_component_maps(root)
    write_jsonl(_architecture_path(root, "requirement_component_map.jsonl"), requirement_rows)
    write_jsonl(_architecture_path(root, "component_requirement_map.jsonl"), component_rows)
    markdown = _architecture_path(root, "ARCHITECTURE_SUMMARY.md")
    markdown.write_text(
        render_architecture_summary(root).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "component_count": summary["component_count"],
        "technology_count": summary["technology_count"],
        "paths": [
            "architecture/architecture_summary.json",
            "architecture/decision_map.json",
            "architecture/requirement_component_map.jsonl",
            "architecture/component_requirement_map.jsonl",
            "architecture/ARCHITECTURE_SUMMARY.md",
        ],
    }


SERVICE_EXTRACTION_SIGNALS = (
    "independent_scaling",
    "security_isolation",
    "failure_isolation",
    "availability_boundary",
    "release_independence",
    "measured_resource_contention",
)


def evaluate_service_proposal(
    signals: Mapping[str, bool], *, evidence_references: Sequence[str]
) -> dict[str, Any]:
    """Apply the architecture anti-complexity gate to a proposed service extraction."""
    recognized = {name: bool(signals.get(name, False)) for name in SERVICE_EXTRACTION_SIGNALS}
    satisfied = sorted(name for name, value in recognized.items() if value)
    evidence = sorted(set(value for value in evidence_references if value.strip()))
    approved = bool(satisfied and evidence)
    return {
        "approved": approved,
        "satisfied_signals": satisfied,
        "evidence_references": evidence,
        "reason": (
            "Extraction is justified by measured boundary evidence."
            if approved
            else "Keep the capability inside the modular monolith until a recognized extraction signal has evidence."
        ),
    }


def validate_architecture(root: Path) -> list[str]:
    errors: list[str] = []
    required_json = (
        "component_catalog.json",
        "technology_stack.json",
        "trust_boundaries.json",
        "state_ownership.json",
        "data_flows.json",
        "deployment_profiles.json",
        "decision_map.json",
    )
    for name in required_json:
        path = _architecture_path(root, name)
        if not path.exists():
            errors.append(f"Architecture artifact is missing: {path.relative_to(root).as_posix()}")
    diagram_dir = _architecture_path(root, "diagrams")
    required_diagrams = {
        "system_context.mmd",
        "component_layers.mmd",
        "authority_and_trust.mmd",
        "durable_command_flow.mmd",
        "deployment_profiles.mmd",
        "traceability_flow.mmd",
    }
    for name in sorted(required_diagrams):
        path = diagram_dir / name
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            errors.append(
                f"Architecture diagram is missing or empty: {path.relative_to(root).as_posix()}"
            )
    if errors:
        return errors

    catalog = load_component_catalog(root)
    components = catalog.get("components", [])
    if catalog.get("component_count") != len(components):
        errors.append("Architecture component_count is stale")
    component_ids: set[str] = set()
    interface_ids: set[str] = set()
    requirement_ids = {
        item["requirement_id"]
        for item in read_jsonl(root / "plans/_traceability/requirements.jsonl")
    }
    adr_catalog = read_json(root / "adr/ADR_CATALOG.json")
    adr_ids = {item["decision_id"] for item in adr_catalog.get("decisions", [])}
    valid_layers = set(catalog.get("layers", []))
    valid_states = {"IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "PLANNED_ONLY"}
    for item in components:
        component_id = item.get("component_id", "")
        if not COMPONENT_ID.fullmatch(component_id):
            errors.append(f"Invalid architecture component ID: {component_id}")
        if component_id in component_ids:
            errors.append(f"Duplicate architecture component ID: {component_id}")
        component_ids.add(component_id)
        if item.get("layer") not in valid_layers:
            errors.append(f"Unknown architecture layer for {component_id}: {item.get('layer')}")
        if item.get("implementation_state") not in valid_states:
            errors.append(
                f"Invalid architecture implementation state for {component_id}: "
                f"{item.get('implementation_state')}"
            )
        if not item.get("responsibility") or not item.get("authority"):
            errors.append(
                f"Architecture component {component_id} lacks responsibility or authority"
            )
        if not item.get("requirement_ids") or not item.get("decision_ids"):
            errors.append(
                f"Architecture component {component_id} lacks requirement or decision linkage"
            )
        for requirement_id in item.get("requirement_ids", []):
            if requirement_id not in requirement_ids:
                errors.append(
                    f"Architecture component {component_id} links unknown requirement {requirement_id}"
                )
        for decision_id in item.get("decision_ids", []):
            if decision_id not in adr_ids:
                errors.append(
                    f"Architecture component {component_id} links unknown ADR {decision_id}"
                )
        for interface in item.get("interfaces_provided", []):
            interface_id = interface.get("interface_id", "")
            if not INTERFACE_ID.fullmatch(interface_id):
                errors.append(f"Invalid interface ID on {component_id}: {interface_id}")
            if interface_id in interface_ids:
                errors.append(f"Duplicate interface ID: {interface_id}")
            interface_ids.add(interface_id)
            if not interface.get("purpose"):
                errors.append(f"Interface {interface_id} lacks a purpose")
    for item in components:
        component_id = item["component_id"]
        for dependency in item.get("depends_on", []):
            if dependency not in component_ids:
                errors.append(
                    f"Architecture component {component_id} depends on unknown component {dependency}"
                )
            if dependency == component_id:
                errors.append(f"Architecture component {component_id} depends on itself")
        for consumed in item.get("interfaces_consumed", []):
            if consumed not in interface_ids:
                errors.append(
                    f"Architecture component {component_id} consumes unknown interface {consumed}"
                )

    boundaries = read_json(_architecture_path(root, "trust_boundaries.json"))
    boundary_ids: set[str] = set()
    for item in boundaries.get("boundaries", []):
        boundary_id = item.get("boundary_id", "")
        if not BOUNDARY_ID.fullmatch(boundary_id):
            errors.append(f"Invalid trust boundary ID: {boundary_id}")
        if boundary_id in boundary_ids:
            errors.append(f"Duplicate trust boundary ID: {boundary_id}")
        boundary_ids.add(boundary_id)
        for component_id in item.get("component_ids", []):
            if component_id not in component_ids:
                errors.append(
                    f"Trust boundary {boundary_id} links unknown component {component_id}"
                )
        if not item.get("controls"):
            errors.append(f"Trust boundary {boundary_id} has no controls")
    if boundaries.get("boundary_count") != len(boundaries.get("boundaries", [])):
        errors.append("Trust boundary count is stale")

    states = read_json(_architecture_path(root, "state_ownership.json"))
    state_entities: set[str] = set()
    if states.get("entity_count") != len(states.get("entities", [])):
        errors.append("State ownership entity_count is stale")
    for item in states.get("entities", []):
        entity = item.get("entity", "")
        if entity in state_entities:
            errors.append(f"Duplicate state ownership entity: {entity}")
        state_entities.add(entity)
        owner = item.get("authoritative_owner")
        if owner not in component_ids:
            errors.append(f"State entity {entity} has unknown owner {owner}")
        if not item.get("persistence") or not item.get("reconciliation_rule"):
            errors.append(f"State entity {entity} lacks persistence or reconciliation rule")

    flows = read_json(_architecture_path(root, "data_flows.json"))
    flow_ids: set[str] = set()
    if flows.get("flow_count") != len(flows.get("flows", [])):
        errors.append("Data-flow count is stale")
    for item in flows.get("flows", []):
        flow_id = item.get("flow_id", "")
        if not FLOW_ID.fullmatch(flow_id):
            errors.append(f"Invalid data-flow ID: {flow_id}")
        if flow_id in flow_ids:
            errors.append(f"Duplicate data-flow ID: {flow_id}")
        flow_ids.add(flow_id)
        for endpoint in (item.get("from_component"), item.get("to_component")):
            if endpoint not in component_ids:
                errors.append(f"Data flow {flow_id} links unknown component {endpoint}")
        for boundary_id in item.get("crosses_boundaries", []):
            if boundary_id not in boundary_ids:
                errors.append(f"Data flow {flow_id} links unknown boundary {boundary_id}")
        if not item.get("contract") or not item.get("failure_rule"):
            errors.append(f"Data flow {flow_id} lacks contract or failure rule")

    profiles = read_json(_architecture_path(root, "deployment_profiles.json"))
    profile_ids: set[str] = set()
    for item in profiles.get("profiles", []):
        profile_id = item.get("profile_id", "")
        if not profile_id or profile_id in profile_ids:
            errors.append(f"Invalid or duplicate deployment profile: {profile_id}")
        profile_ids.add(profile_id)
        for component_id in item.get("required_components", []):
            if component_id not in component_ids:
                errors.append(
                    f"Deployment profile {profile_id} links unknown component {component_id}"
                )
        if not item.get("degraded_mode") or not item.get("network_rule"):
            errors.append(f"Deployment profile {profile_id} lacks degraded mode or network rule")

    stack = load_technology_stack(root)
    technologies = stack.get("technologies", [])
    if stack.get("technology_count") != len(technologies):
        errors.append("Technology count is stale")
    technology_ids: set[str] = set()
    upstream_entries = {
        item["upstream_id"]: item
        for item in read_json(root / "provenance/upstream_registry.json").get("entries", [])
    }
    lifecycle = {
        "SELECTED",
        "QUALIFIED_FALLBACK",
        "PROFILE_OPTIONAL",
        "DEFERRED",
        "ACTIVATION_BLOCKED",
    }
    for item in technologies:
        technology_id = item.get("technology_id", "")
        if not TECHNOLOGY_ID.fullmatch(technology_id):
            errors.append(f"Invalid technology ID: {technology_id}")
        if technology_id in technology_ids:
            errors.append(f"Duplicate technology ID: {technology_id}")
        technology_ids.add(technology_id)
        if item.get("lifecycle_status") not in lifecycle:
            errors.append(
                f"Invalid lifecycle status for {technology_id}: {item.get('lifecycle_status')}"
            )
        if item.get("decision_id") not in adr_ids:
            errors.append(f"Technology {technology_id} links unknown ADR {item.get('decision_id')}")
        if not item.get("constraints"):
            errors.append(f"Technology {technology_id} lacks bounded-use constraints")
        for component_id in item.get("component_ids", []):
            if component_id not in component_ids:
                errors.append(f"Technology {technology_id} links unknown component {component_id}")
        for upstream_id in item.get("upstream_ids", []):
            if upstream_id not in upstream_entries:
                errors.append(f"Technology {technology_id} links unknown upstream {upstream_id}")
            elif (
                item.get("lifecycle_status") == "SELECTED"
                and upstream_entries[upstream_id].get("disposition") != "ADOPT_DEPENDENCY"
            ):
                errors.append(
                    f"Selected technology {technology_id} links non-adopted upstream {upstream_id}"
                )

    observed_decision_map = read_json(_architecture_path(root, "decision_map.json"))
    if observed_decision_map != build_decision_map(root):
        errors.append("Architecture decision map is stale")
    expected_requirement_rows, expected_component_rows = build_requirement_component_maps(root)
    requirement_map_path = _architecture_path(root, "requirement_component_map.jsonl")
    component_map_path = _architecture_path(root, "component_requirement_map.jsonl")
    if (
        not requirement_map_path.exists()
        or read_jsonl(requirement_map_path) != expected_requirement_rows
    ):
        errors.append("Architecture requirement/component maps are stale")
    if not component_map_path.exists() or read_jsonl(component_map_path) != expected_component_rows:
        errors.append("Architecture component/requirement maps are stale")
    for decision in adr_catalog.get("decisions", []):
        if decision.get("status") == "ACCEPTED":
            if not decision.get("source_references"):
                errors.append(f"Accepted ADR {decision['decision_id']} lacks source references")
            if not decision.get("requirement_ids"):
                errors.append(f"Accepted ADR {decision['decision_id']} lacks requirement links")
            if not decision.get("component_ids"):
                errors.append(
                    f"Accepted ADR {decision['decision_id']} lacks affected component links"
                )
            for requirement_id in decision.get("requirement_ids", []):
                if requirement_id not in requirement_ids:
                    errors.append(
                        f"ADR {decision['decision_id']} links unknown requirement {requirement_id}"
                    )
            for component_id in decision.get("component_ids", []):
                if component_id not in component_ids:
                    errors.append(
                        f"ADR {decision['decision_id']} links unknown component {component_id}"
                    )
            path = root / decision["path"]
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            for heading in (
                "## Context",
                "## Decision",
                "## Alternatives considered",
                "## Consequences",
            ):
                if heading not in text:
                    errors.append(f"Accepted ADR {decision['decision_id']} lacks section {heading}")

    summary_path = _architecture_path(root, "architecture_summary.json")
    markdown_path = _architecture_path(root, "ARCHITECTURE_SUMMARY.md")
    if not summary_path.exists() or read_json(summary_path) != summarize_architecture(root):
        errors.append("Generated architecture summary JSON is missing or stale")
    expected_markdown = render_architecture_summary(root).rstrip() + "\n"
    if not markdown_path.exists() or markdown_path.read_text(encoding="utf-8") != expected_markdown:
        errors.append("Generated architecture summary Markdown is missing or stale")
    return errors
