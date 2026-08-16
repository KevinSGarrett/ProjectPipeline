from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from project_pipeline.agent_router.adapters import MockProviderAdapter, ProviderAdapterError
from project_pipeline.agent_router.registry import build_registry
from project_pipeline.agent_router.service import AgentRouterService
from project_pipeline.domain.agents import (
    AgentSpec,
    CapabilityRoutePolicy,
    CapabilitySpec,
    ExecutionMode,
    ExecutionTaskContract,
    ModelSpec,
    ProviderRuntimeState,
    ProviderSpec,
    ProviderStateObservation,
    QualificationState,
)


def simulate_provider_failover() -> dict[str, Any]:
    now = datetime.now(UTC)
    cap = CapabilitySpec(
        capability_id="routine_reasoning", description="Routine advisory reasoning"
    )
    providers = (
        ProviderSpec(
            provider_id="provider:primary",
            display_name="Primary",
            adapter_id="adapter:mock-provider",
            execution_mode=ExecutionMode.MOCK,
            capabilities=(cap.capability_id,),
        ),
        ProviderSpec(
            provider_id="provider:fallback",
            display_name="Fallback",
            adapter_id="adapter:mock-fallback",
            execution_mode=ExecutionMode.MOCK,
            capabilities=(cap.capability_id,),
            local=True,
        ),
    )
    models = (
        ModelSpec(
            model_id="model:primary",
            provider_id="provider:primary",
            provider_model_name="primary",
            version="1",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
        ),
        ModelSpec(
            model_id="model:fallback",
            provider_id="provider:fallback",
            provider_model_name="fallback",
            version="1",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
            local=True,
        ),
    )
    agents = (
        AgentSpec(
            agent_id="agent:primary",
            model_id="model:primary",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
        ),
        AgentSpec(
            agent_id="agent:fallback",
            model_id="model:fallback",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
        ),
    )
    registry = build_registry(
        capabilities=(cap,),
        providers=providers,
        models=models,
        agents=agents,
        routing_policies=(
            CapabilityRoutePolicy(
                capability_id=cap.capability_id,
                preferred_provider_ids=("provider:primary",),
                fallback_provider_ids=("provider:fallback",),
            ),
        ),
        when=now,
    )
    primary = MockProviderAdapter(
        "provider:primary",
        [
            ProviderAdapterError(
                "simulated outage", kind="UNAVAILABLE", retryable=True, provider_state="UNAVAILABLE"
            )
        ],
    )
    primary.adapter_id = "adapter:mock-provider"
    fallback = MockProviderAdapter("provider:fallback")
    fallback.adapter_id = "adapter:mock-fallback"
    contract = ExecutionTaskContract(
        task_id="SIM-TASK",
        task_class="reasoning",
        required_capabilities=(cap.capability_id,),
        instructions="Simulate failover",
    )
    states = [
        ProviderStateObservation(
            provider_id=x.provider_id, state=ProviderRuntimeState.HEALTHY, observed_at_utc=now
        )
        for x in providers
    ]
    receipt = AgentRouterService(
        registry, {primary.adapter_id: primary, fallback.adapter_id: fallback}
    ).execute(contract, states, [])
    return {
        "scenario": "provider_failover",
        "succeeded": receipt.succeeded,
        "attempt_count": len(receipt.attempts),
        "providers": [x.provider_id for x in receipt.attempts],
        "result": receipt.model_dump(mode="json"),
    }
