from __future__ import annotations

from pathlib import Path

from project_pipeline.domain.context import ContextPolicy
from project_pipeline.io import read_json, read_jsonl
from project_pipeline.persistence.migrations import load_migration_catalog
from project_pipeline.upstream import IMPLEMENTED_USAGE_STATES

_REQUIRED_PATHS = (
    "config/context_policy.json",
    "src/project_pipeline/domain/context.py",
    "src/project_pipeline/context_engine/broker.py",
    "src/project_pipeline/context_engine/compiler.py",
    "src/project_pipeline/context_engine/firewall.py",
    "src/project_pipeline/context_engine/persistence.py",
    "src/project_pipeline/context_engine/service.py",
    "src/project_pipeline/context_engine/trust.py",
    "src/project_pipeline/upstream_integrations/context.py",
    "database/migrations/sqlite/PPDB-0009_context_delegation.up.sql",
    "database/migrations/sqlite/PPDB-0009_context_delegation.down.sql",
    "database/migrations/postgresql/PPDB-0009_context_delegation.up.sql",
    "database/migrations/postgresql/PPDB-0009_context_delegation.down.sql",
    "docs/architecture/context_and_delegation.md",
    "runbooks/context_pack_recovery.md",
    "plans/05_context_and_knowledge/PLAN-CTX-002_context_delegation_implementation.md",
)

_CONTEXT_UPSTREAM_IDS = {
    "UPSTREAM-115",
    "UPSTREAM-062",
    "UPSTREAM-030",
    "UPSTREAM-080",
    "UPSTREAM-052",
}


def validate_context_foundation(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"context foundation path is missing: {relative}")

    policy_path = root / "config" / "context_policy.json"
    if policy_path.exists():
        try:
            ContextPolicy.model_validate(read_json(policy_path))
        except Exception as error:
            errors.append(f"context policy is invalid: {error}")

    try:
        catalog = load_migration_catalog(root)
        migration = next(
            (item for item in catalog.migrations if item.migration_id == "PPDB-0009"), None
        )
        if migration is None:
            errors.append("context migration PPDB-0009 is missing from the migration catalog")
        elif migration.name != "context_delegation":
            errors.append("PPDB-0009 has an unexpected migration name")
    except Exception as error:
        errors.append(f"context migration catalog cannot be loaded: {error}")

    gate_path = root / "provenance" / "upstream_adoption_gate.json"
    if not gate_path.exists():
        errors.append("context upstream adoption gate is missing")
    else:
        gate = read_json(gate_path).get("subsystems", {}).get("context_and_delegation")
        if not gate:
            errors.append("context_and_delegation upstream gate record is missing")
        else:
            candidates = set(gate.get("candidate_upstream_ids", []))
            if candidates != _CONTEXT_UPSTREAM_IDS:
                errors.append(
                    "context upstream candidate set differs from the governed five-repository set"
                )
            if gate.get("review_state") != "INTEGRATED":
                errors.append("context upstream gate has not reached INTEGRATED review state")

    usage_path = root / "provenance" / "upstream_usage.jsonl"
    if usage_path.exists():
        usage = {item["upstream_id"]: item for item in read_jsonl(usage_path)}
        for upstream_id in ("UPSTREAM-115", "UPSTREAM-062", "UPSTREAM-030"):
            record = usage.get(upstream_id, {})
            if record.get("usage_state") not in IMPLEMENTED_USAGE_STATES:
                errors.append(f"context upstream {upstream_id} lacks implemented usage")
            if not record.get("integration_paths"):
                errors.append(f"context upstream {upstream_id} lacks integration paths")
        expected_patterns = {
            "UPSTREAM-080": "IMPLEMENTATION_PATTERN_ADOPTED",
            "UPSTREAM-052": "ARCHITECTURE_PATTERN_ADOPTED",
        }
        for upstream_id, expected in expected_patterns.items():
            if usage.get(upstream_id, {}).get("usage_state") != expected:
                errors.append(f"context upstream {upstream_id} is not recorded as {expected}")
    else:
        errors.append("upstream usage ledger is missing")

    return errors
