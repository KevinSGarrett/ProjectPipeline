from __future__ import annotations

from pathlib import Path

from project_pipeline.agent_router.adapters import MockToolAdapter
from project_pipeline.agent_router.registry import load_agent_registry
from project_pipeline.agent_router.simulation import (
    simulate_circuit_open_and_recovery,
    simulate_provider_failover,
)
from project_pipeline.agent_router.tools import GovernedToolBoundary
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
    try:
        failover = simulate_provider_failover()
        circuit = simulate_circuit_open_and_recovery()
        if not failover.get("succeeded") or not circuit.get("closed"):
            errors.append("agent router integrated journey failed")
        registry = load_agent_registry(root)
        tool = next(iter(registry.tools), None)
        if tool is not None:
            boundary = GovernedToolBoundary(
                {tool.tool_id: tool},
                {tool.adapter_id: MockToolAdapter({tool.tool_id: {"read"}})},
                workspace_root=root,
                allowed_operations={tool.tool_id: {"read"}},
            )
            try:
                boundary.invoke("tool:missing", "read", {})
                errors.append("governed tool boundary failed to deny an unlisted tool")
            except Exception as error:
                _denied = str(error)
                del _denied
    except Exception as error:
        errors.append(f"agent router integrated journey is invalid: {error}")
    return errors
