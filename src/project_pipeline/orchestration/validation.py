from __future__ import annotations

from pathlib import Path

from project_pipeline.domain.orchestration import OrchestrationPolicy
from project_pipeline.io import read_json, read_jsonl
from project_pipeline.persistence.migrations import load_migration_catalog
from project_pipeline.upstream import IMPLEMENTED_USAGE_STATES

_REQUIRED_PATHS = (
    "config/orchestration_policy.json",
    "src/project_pipeline/domain/orchestration.py",
    "src/project_pipeline/orchestration/ports.py",
    "src/project_pipeline/orchestration/persistence.py",
    "src/project_pipeline/orchestration/runtime.py",
    "src/project_pipeline/orchestration/recovery.py",
    "src/project_pipeline/orchestration/adapters.py",
    "src/project_pipeline/orchestration/service.py",
    "src/project_pipeline/orchestration/simulation.py",
    "database/migrations/sqlite/PPDB-0010_durable_orchestration_recovery.up.sql",
    "database/migrations/sqlite/PPDB-0010_durable_orchestration_recovery.down.sql",
    "database/migrations/postgresql/PPDB-0010_durable_orchestration_recovery.up.sql",
    "database/migrations/postgresql/PPDB-0010_durable_orchestration_recovery.down.sql",
    "provenance/reviews/PASS-13_orchestration_upstream_review.md",
    "provenance/pass_13_orchestration_gate.json",
    "docs/architecture/durable_orchestration_recovery.md",
    "runbooks/orchestration_recovery.md",
    "plans/06_orchestration/PLAN-ORCH-001_durable_orchestration_recovery.md",
)

_ORCHESTRATION_UPSTREAM_IDS = {
    "UPSTREAM-002",
    "UPSTREAM-005",
    "UPSTREAM-018",
    "UPSTREAM-020",
    "UPSTREAM-025",
    "UPSTREAM-026",
    "UPSTREAM-050",
    "UPSTREAM-054",
    "UPSTREAM-056",
    "UPSTREAM-061",
    "UPSTREAM-074",
    "UPSTREAM-088",
    "UPSTREAM-095",
    "UPSTREAM-096",
    "UPSTREAM-102",
    "UPSTREAM-104",
    "UPSTREAM-107",
    "UPSTREAM-109",
}


def validate_orchestration_foundation(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"orchestration foundation path is missing: {relative}")

    policy_path = root / "config" / "orchestration_policy.json"
    if policy_path.exists():
        try:
            policy = OrchestrationPolicy.model_validate(read_json(policy_path))
            if policy.allow_active_backend_migration:
                errors.append(
                    "orchestration policy must not permit silent active-backend migration"
                )
            if policy.blind_retry_unknown_outcome:
                errors.append("orchestration policy must forbid blind retry of unknown outcomes")
        except Exception as error:
            errors.append(f"orchestration policy is invalid: {error}")

    try:
        catalog = load_migration_catalog(root)
        migration = next(
            (item for item in catalog.migrations if item.migration_id == "PPDB-0010"), None
        )
        if migration is None:
            errors.append("orchestration migration PPDB-0010 is missing from the migration catalog")
        elif migration.name != "durable_orchestration_recovery":
            errors.append("PPDB-0010 has an unexpected migration name")
    except Exception as error:
        errors.append(f"orchestration migration catalog cannot be loaded: {error}")

    gate_path = root / "provenance" / "upstream_adoption_gate.json"
    if gate_path.exists():
        gate = (
            read_json(gate_path)
            .get("subsystems", {})
            .get("orchestration_and_parallel_execution", {})
        )
        if set(gate.get("candidate_upstream_ids", [])) != _ORCHESTRATION_UPSTREAM_IDS:
            errors.append(
                "orchestration upstream candidate set differs from the governed 18-repository set"
            )
        if gate.get("review_state") not in {"FOCUSED_REVIEW_COMPLETE", "INTEGRATED"}:
            errors.append("orchestration upstream review was not completed before implementation")
    else:
        errors.append("orchestration upstream adoption gate is missing")

    pass_gate = root / "provenance" / "pass_13_orchestration_gate.json"
    if not pass_gate.exists():
        errors.append("Pass 13 orchestration upstream gate record is missing")
    else:
        record = read_json(pass_gate)
        if not record.get("material_implementation_allowed"):
            errors.append("Pass 13 orchestration gate does not permit material implementation")
        if record.get("candidate_count") != 18:
            errors.append("Pass 13 orchestration gate candidate count is stale")

    usage_path = root / "provenance" / "upstream_usage.jsonl"
    if usage_path.exists():
        usage = {item["upstream_id"]: item for item in read_jsonl(usage_path)}
        hatchet = usage.get("UPSTREAM-050", {})
        if hatchet.get("usage_state") not in IMPLEMENTED_USAGE_STATES:
            errors.append("Hatchet lacks a concrete implemented adapter usage record")
        if not hatchet.get("integration_paths"):
            errors.append("Hatchet implemented usage lacks integration paths")
        if usage.get("UPSTREAM-074", {}).get("usage_state") != "ARCHITECTURE_PATTERN_ADOPTED":
            errors.append(
                "Symphony orchestrator/runner architecture pattern is not recorded as adopted"
            )
        if usage.get("UPSTREAM-095", {}).get("usage_state") != "IMPLEMENTATION_PATTERN_ADOPTED":
            errors.append(
                "Bernstein deterministic recovery/audit implementation pattern is not recorded as adopted"
            )
    else:
        errors.append("upstream usage ledger is missing")
    return errors
