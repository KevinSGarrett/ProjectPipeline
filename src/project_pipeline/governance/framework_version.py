"""Record and surface platform/policy-framework version drift."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.io import read_json


def evaluate_framework_version(root: Path) -> dict[str, Any]:
    """Compare the recorded qualified versions to the live catalogs."""

    root = root.resolve()
    recorded = read_json(root / "config" / "version_compatibility.json")
    catalog = read_json(root / "database" / "MIGRATION_CATALOG.json")
    migrations = [
        str(item.get("migration_id"))
        for item in catalog.get("migrations", [])
        if isinstance(item, dict) and item.get("migration_id")
    ]
    observed_latest = max(migrations) if migrations else None
    instruction_manifest = read_json(root / "instructions" / "INSTRUCTION_MANIFEST.json")
    drift: list[str] = []
    if recorded.get("latest_database_migration") != observed_latest:
        drift.append("database_migration")
    if not str(recorded.get("platform_version") or "").strip():
        drift.append("platform_version_missing")
    if not str(recorded.get("schema_version") or "").strip():
        drift.append("policy_framework_version_missing")
    return {
        "schema_version": "1.0.0",
        "ok": not drift,
        "platform_version": recorded.get("platform_version"),
        "policy_framework_version": recorded.get("schema_version"),
        "recorded_latest_database_migration": recorded.get("latest_database_migration"),
        "observed_latest_database_migration": observed_latest,
        "instruction_manifest_present": bool(instruction_manifest),
        "drift": drift,
        "user_action_required": False,
    }
