from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.agent_router.pydantic_ai_adapter import PydanticAIProviderAdapter
from project_pipeline.agent_router.registry import load_agent_registry
from project_pipeline.agent_router.router import AgentRouter
from project_pipeline.domain import (
    ExecutionTaskContract,
    ProviderRuntimeState,
    ProviderStateObservation,
)


def contract():
    return ExecutionTaskContract(
        task_id="T",
        task_class="reasoning",
        required_capabilities=("routine_reasoning",),
        instructions="hello",
    )


class Usage:
    input_tokens = 4
    output_tokens = 2
    cache_read_tokens = 1
    requests = 1


class Result:
    output = "typed-ok"

    def usage(self):
        return Usage()


class FakeAgent:
    def __init__(self, model, **kwargs):
        self.model = model
        self.kwargs = kwargs

    def run_sync(self, prompt):
        assert prompt == "hello"
        return Result()


def test_pydantic_ai_adapter_uses_typed_framework_boundary_and_upstream_contract() -> None:
    adapter = PydanticAIProviderAdapter(agent_factory=FakeAgent)
    health = adapter.health()
    assert health["installed"] is True
    assert health["upstream_id"] == "UPSTREAM-086"
    result = adapter.execute(contract(), model_name="openai:test-model")
    assert result.output == {"text": "typed-ok"}
    assert result.usage.input_units == 4
    assert "UPSTREAM-086" in result.evidence_references


def test_pydantic_ai_registry_entry_is_quarantined_and_has_no_routing_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_agent_registry(root)
    provider = next(
        item for item in registry.providers if item.provider_id == "provider:pydantic-ai"
    )
    assert provider.enabled is False
    assert provider.adapter_id == "adapter:pydantic-ai"
    now = datetime.now(UTC)
    states = [
        ProviderStateObservation(
            provider_id=item.provider_id, state=ProviderRuntimeState.HEALTHY, observed_at_utc=now
        )
        for item in registry.providers
    ]
    decision = AgentRouter().route(
        ExecutionTaskContract(
            task_id="T",
            task_class="reasoning",
            required_capabilities=("routine_reasoning",),
            instructions="advisory only",
        ),
        registry,
        states,
        [],
    )
    assert decision.selected_provider_id != "provider:pydantic-ai"
