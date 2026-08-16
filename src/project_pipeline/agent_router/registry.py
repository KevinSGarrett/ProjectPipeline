from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from project_pipeline.domain.agents import (
    AgentRegistrySnapshot,
    AgentSpec,
    CapabilityRoutePolicy,
    CapabilitySpec,
    ModelSpec,
    ProviderSpec,
    ToolSpec,
    agent_fingerprint,
    router_identifier,
)


def build_registry(
    *,
    capabilities: Sequence[CapabilitySpec],
    providers: Sequence[ProviderSpec],
    models: Sequence[ModelSpec],
    agents: Sequence[AgentSpec],
    tools: Sequence[ToolSpec] = (),
    routing_policies: Sequence[CapabilityRoutePolicy] = (),
    when: datetime | None = None,
) -> AgentRegistrySnapshot:
    when = (when or datetime.now(UTC)).astimezone(UTC)
    payload = {
        "capabilities": [item.model_dump(mode="json") for item in capabilities],
        "providers": [item.model_dump(mode="json") for item in providers],
        "models": [item.model_dump(mode="json") for item in models],
        "agents": [item.model_dump(mode="json") for item in agents],
        "tools": [item.model_dump(mode="json") for item in tools],
        "routing_policies": [item.model_dump(mode="json") for item in routing_policies],
    }
    return AgentRegistrySnapshot(
        registry_id=router_identifier("REG", agent_fingerprint(payload)),
        capabilities=tuple(capabilities),
        providers=tuple(providers),
        models=tuple(models),
        agents=tuple(agents),
        tools=tuple(tools),
        routing_policies=tuple(routing_policies),
        generated_at_utc=when,
    )


def load_agent_registry(root: Path, *, when: datetime | None = None) -> AgentRegistrySnapshot:
    base = root / "config" / "agents"

    def load(name: str) -> list[object]:
        return cast(list[object], json.loads((base / name).read_text(encoding="utf-8")))

    return build_registry(
        capabilities=[CapabilitySpec.model_validate(x) for x in load("capabilities.json")],
        providers=[ProviderSpec.model_validate(x) for x in load("providers.json")],
        models=[ModelSpec.model_validate(x) for x in load("models.json")],
        agents=[AgentSpec.model_validate(x) for x in load("agents.json")],
        tools=[ToolSpec.model_validate(x) for x in load("tools.json")],
        routing_policies=[
            CapabilityRoutePolicy.model_validate(x) for x in load("routing_policy.json")
        ],
        when=when,
    )
