"""Modular instruction-system coverage for REQ-GOV-0006."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.io import read_json

REQUIRED_MODULES: dict[str, tuple[str, ...]] = {
    "governance": ("authority", "autonomous_cycle"),
    "git": ("git", "github"),
    "jira": ("jira",),
    "security": ("security", "secrets"),
    "testing": ("testing", "evidence"),
    "environments": ("windows_compatibility", "remote_machines"),
    "deployment": ("release", "post_merge"),
    "project_profile": ("authority", "project_identity"),
}


def evaluate_instruction_system(root: Path) -> dict[str, Any]:
    """Prove every required module maps to a present primary instruction."""

    root = root.resolve()
    matrix = read_json(root / "instructions" / "INSTRUCTION_COVERAGE_MATRIX.json")
    domains = {
        str(item.get("domain")): item
        for item in matrix.get("domains", [])
        if isinstance(item, dict) and item.get("domain")
    }
    modules: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for module, aliases in REQUIRED_MODULES.items():
        matched = None
        for alias in aliases:
            entry = domains.get(alias)
            if entry is None:
                continue
            primary = root / str(entry.get("primary") or "")
            if primary.is_file():
                matched = {
                    "coverage_domain": alias,
                    "primary": str(entry.get("primary")),
                    "present": True,
                }
                break
        if matched is None:
            missing.append(module)
            modules[module] = {"coverage_domain": None, "primary": None, "present": False}
        else:
            modules[module] = matched
    return {
        "schema_version": "1.0.0",
        "ok": not missing,
        "missing_modules": missing,
        "modules": modules,
        "user_action_required": False,
    }
