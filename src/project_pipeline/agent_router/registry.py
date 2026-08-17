from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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

_SECRET_VALUE = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|ghp_[a-z0-9]{20,}|xoxb-[a-z0-9-]{20,}|api[_-]?key\s*[:=]\s*\S+)"
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
    encoded = json.dumps(payload, sort_keys=True)
    if _SECRET_VALUE.search(encoded):
        raise ValueError("registry payload must reference secrets, not secret values")
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


def execution_targets(registry: AgentRegistrySnapshot) -> tuple[dict[str, Any], ...]:
    providers = {item.provider_id: item for item in registry.providers}
    return tuple(
        {
            "target_id": model.model_id,
            "provider_id": model.provider_id,
            "adapter_id": providers[model.provider_id].adapter_id,
            "enabled": providers[model.provider_id].enabled,
            "qualification": model.qualification.value,
            "local": model.local or providers[model.provider_id].local,
        }
        for model in registry.models
        if model.provider_id in providers
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
