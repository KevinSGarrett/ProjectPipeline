from datetime import UTC, datetime

from project_pipeline.agent_router import AgentRouter, build_registry
from project_pipeline.domain import (
    AgentSpec,
    CapabilityRoutePolicy,
    CapabilitySpec,
    CircuitBreakerRecord,
    CircuitState,
    ExecutionMode,
    ExecutionTaskContract,
    ModelSpec,
    ProviderRuntimeState,
    ProviderSpec,
    ProviderStateObservation,
    QualificationState,
)


def make_registry(primary_state=QualificationState.QUALIFIED):
    cap1 = CapabilitySpec(capability_id="code_implementation", description="code")
    cap2 = CapabilitySpec(capability_id="repository_reasoning", description="repo")
    p1 = ProviderSpec(
        provider_id="provider:one",
        display_name="One",
        adapter_id="adapter:one",
        execution_mode=ExecutionMode.MOCK,
        capabilities=(cap1.capability_id, cap2.capability_id),
    )
    p2 = ProviderSpec(
        provider_id="provider:two",
        display_name="Two",
        adapter_id="adapter:two",
        execution_mode=ExecutionMode.MOCK,
        capabilities=(cap1.capability_id, cap2.capability_id),
        local=True,
    )
    m1 = ModelSpec(
        model_id="model:one",
        provider_id=p1.provider_id,
        provider_model_name="one",
        version="1",
        capabilities=p1.capabilities,
        qualification=primary_state,
        quality_tier="strong",
    )
    m2 = ModelSpec(
        model_id="model:two",
        provider_id=p2.provider_id,
        provider_model_name="two",
        version="1",
        capabilities=p2.capabilities,
        qualification=QualificationState.QUALIFIED,
        quality_tier="strong",
        local=True,
    )
    a1 = AgentSpec(
        agent_id="agent:one",
        model_id=m1.model_id,
        capabilities=p1.capabilities,
        qualification=primary_state,
    )
    a2 = AgentSpec(
        agent_id="agent:two",
        model_id=m2.model_id,
        capabilities=p2.capabilities,
        qualification=QualificationState.QUALIFIED,
    )
    pol = CapabilityRoutePolicy(
        capability_id=cap1.capability_id,
        preferred_provider_ids=(p1.provider_id,),
        fallback_provider_ids=(p2.provider_id,),
    )
    return build_registry(
        capabilities=(cap1, cap2),
        providers=(p1, p2),
        models=(m1, m2),
        agents=(a1, a2),
        routing_policies=(pol,),
    )


def req(**kwargs):
    data = dict(
        task_id="T",
        task_class="implementation",
        required_capabilities=("code_implementation", "repository_reasoning"),
        quality_tier="strong",
        instructions="do bounded work",
    )
    data.update(kwargs)
    return ExecutionTaskContract(**data)


def states(one=ProviderRuntimeState.HEALTHY, two=ProviderRuntimeState.HEALTHY):
    now = datetime.now(UTC)
    return [
        ProviderStateObservation(provider_id="provider:one", state=one, observed_at_utc=now),
        ProviderStateObservation(provider_id="provider:two", state=two, observed_at_utc=now),
    ]


def test_capability_first_selects_preferred_eligible_provider():
    decision = AgentRouter().route(req(), make_registry(), states(), [])
    assert decision.selected_provider_id == "provider:one"


def test_unavailable_preferred_falls_back_without_changing_task_contract():
    decision = AgentRouter().route(
        req(), make_registry(), states(ProviderRuntimeState.UNAVAILABLE), []
    )
    assert (
        decision.selected_provider_id == "provider:two"
        and decision.required_capabilities == req().required_capabilities
    )


def test_quarantined_preferred_is_ineligible():
    decision = AgentRouter().route(
        req(), make_registry(QualificationState.QUARANTINED), states(), []
    )
    assert decision.selected_provider_id == "provider:two"


def test_open_circuit_excludes_provider():
    now = datetime.now(UTC)
    circuit = CircuitBreakerRecord(
        provider_id="provider:one",
        state=CircuitState.OPEN,
        consecutive_failures=3,
        opened_at_utc=now,
        updated_at_utc=now,
    )
    decision = AgentRouter().route(req(), make_registry(), states(), [circuit], now=now)
    assert decision.selected_provider_id == "provider:two"


def test_data_egress_policy_can_force_local_route():
    registry = make_registry()
    # provider one is remote by default, provider two local but still defaults data_egress=True; make it private.
    p2 = registry.providers[1].model_copy(update={"data_egress": False})
    registry = registry.model_copy(update={"providers": (registry.providers[0], p2)})
    decision = AgentRouter().route(req(allow_data_egress=False), registry, states(), [])
    assert decision.selected_provider_id == "provider:two"


def test_prefer_local_under_pressure_outranks_degraded_preferred():
    decision = AgentRouter().route(
        req(), make_registry(), states(ProviderRuntimeState.DEGRADED), []
    )
    assert decision.selected_provider_id == "provider:two"
    healthy = AgentRouter().route(req(), make_registry(), states(), [])
    assert healthy.selected_provider_id == "provider:one"


def test_no_capability_match_fails_closed():
    decision = AgentRouter().route(
        ExecutionTaskContract(
            task_id="T", task_class="x", required_capabilities=("visual_review",), instructions="x"
        ),
        make_registry(),
        states(),
        [],
    )
    assert (
        decision.selected_provider_id is None and "no_capability_match" in decision.no_route_reasons
    )
