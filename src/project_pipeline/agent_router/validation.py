from __future__ import annotations

from pathlib import Path

from project_pipeline.agent_router.registry import load_agent_registry
from project_pipeline.persistence import load_migration_catalog, validate_migration_catalog

_REQUIRED = (
    "src/project_pipeline/domain/agents.py",
    "src/project_pipeline/agent_router/router.py",
    "src/project_pipeline/agent_router/circuit.py",
    "src/project_pipeline/agent_router/adapters.py",
    "src/project_pipeline/agent_router/persistence.py",
    "src/project_pipeline/agent_router/qualification.py",
    "plans/06_agents_models_and_tools/PLAN-AGENT-002_agent_router_provider_abstraction.md",
)


def validate_agent_router_foundation(root: Path) -> list[str]:
    errors = [
        f"agent router foundation file is missing: {p}"
        for p in _REQUIRED
        if not (root / p).exists()
    ]
    errors.extend(validate_migration_catalog(root))
    try:
        load_agent_registry(root)
    except Exception as error:
        errors.append(f"agent registry is invalid: {error}")
    if not errors:
        catalog = load_migration_catalog(root)
        if not any(item.migration_id == "PPDB-0008" for item in catalog.migrations):
            errors.append("agent router migration PPDB-0008 is not registered")
    return errors
