from datetime import UTC, datetime

from project_pipeline.agent_router import (
    AgentRouterService,
    MockProviderAdapter,
    ProviderAdapterError,
    build_registry,
)
from project_pipeline.domain import (
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


def setup():
    cap = CapabilitySpec(capability_id="routine_reasoning", description="reason")
    ps = [
        ProviderSpec(
            provider_id=f"provider:{x}",
            display_name=x,
            adapter_id=f"adapter:{x}",
            execution_mode=ExecutionMode.MOCK,
            capabilities=(cap.capability_id,),
        )
        for x in ("one", "two")
    ]
    ms = [
        ModelSpec(
            model_id=f"model:{x}",
            provider_id=f"provider:{x}",
            provider_model_name=x,
            version="1",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
        )
        for x in ("one", "two")
    ]
    agents = [
        AgentSpec(
            agent_id=f"agent:{x}",
            model_id=f"model:{x}",
            capabilities=(cap.capability_id,),
            qualification=QualificationState.QUALIFIED,
        )
        for x in ("one", "two")
    ]
    reg = build_registry(
        capabilities=(cap,),
        providers=ps,
        models=ms,
        agents=agents,
        routing_policies=(
            CapabilityRoutePolicy(
                capability_id=cap.capability_id,
                preferred_provider_ids=("provider:one",),
                fallback_provider_ids=("provider:two",),
            ),
        ),
    )
    now = datetime.now(UTC)
    states = [
        ProviderStateObservation(
            provider_id=p.provider_id, state=ProviderRuntimeState.HEALTHY, observed_at_utc=now
        )
        for p in ps
    ]
    contract = ExecutionTaskContract(
        task_id="T", task_class="x", required_capabilities=(cap.capability_id,), instructions="x"
    )
    return reg, states, contract


def test_service_falls_back_after_provider_failure():
    reg, states, contract = setup()
    one = MockProviderAdapter(
        "provider:one", [ProviderAdapterError("down", kind="UNAVAILABLE", retryable=True)]
    )
    one.adapter_id = "adapter:one"
    two = MockProviderAdapter("provider:two")
    two.adapter_id = "adapter:two"
    receipt = AgentRouterService(reg, {"adapter:one": one, "adapter:two": two}).execute(
        contract, states, []
    )
    assert receipt.succeeded and [x.provider_id for x in receipt.attempts] == [
        "provider:one",
        "provider:two",
    ]


def test_service_reports_failed_receipt_when_all_candidates_fail():
    reg, states, contract = setup()
    adapters = {}
    for name in ("one", "two"):
        a = MockProviderAdapter(
            f"provider:{name}", [ProviderAdapterError("down", kind="UNAVAILABLE", retryable=True)]
        )
        a.adapter_id = f"adapter:{name}"
        adapters[a.adapter_id] = a
    receipt = AgentRouterService(reg, adapters).execute(contract, states, [])
    assert not receipt.succeeded and len(receipt.attempts) == 2
