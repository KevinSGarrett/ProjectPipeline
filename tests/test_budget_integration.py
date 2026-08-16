from datetime import UTC, datetime

from project_pipeline.agent_router.router import AgentRouter
from project_pipeline.budget.integration import (
    apply_budget_admission_to_scheduler,
    paid_lane_ceiling,
)
from project_pipeline.domain.agents import (
    AgentRegistrySnapshot,
    AgentSpec,
    CapabilityRoutePolicy,
    CapabilitySpec,
    CircuitBreakerRecord,
    ExecutionMode,
    ExecutionTaskContract,
    ModelSpec,
    PerformanceObservation,
    ProviderRuntimeState,
    ProviderSpec,
    ProviderStateObservation,
    QualificationState,
)
from project_pipeline.domain.budget import BudgetAdmissionDecision, PressureMode, budget_identifier
from project_pipeline.domain.scheduler import SchedulerTaskProfile

NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)


def test_scheduler_profile_remains_ineligible_when_budget_denies():
    profile = SchedulerTaskProfile(
        task_id="PP-TASK-000001",
        project_id="PROJECT-PIPELINE",
        sequence_rank=1,
        utility_score=100,
        priority="P1",
        policy_eligible=True,
    )
    decision = BudgetAdmissionDecision(
        decision_id=budget_identifier("ADMISSION", "PP-TASK-000001", "x"),
        task_id="PP-TASK-000001",
        admitted=False,
        pressure_mode=PressureMode.RED,
        authorized_microunits=0,
        allowed_paid_incremental=False,
        generated_at_utc=NOW,
    )
    result = apply_budget_admission_to_scheduler((profile,), {profile.task_id: decision})
    assert result[0].policy_eligible is False


def test_paid_lane_ceiling_reduces_with_pressure():
    assert paid_lane_ceiling(8, PressureMode.GREEN) == 8
    assert paid_lane_ceiling(8, PressureMode.YELLOW) == 6
    assert paid_lane_ceiling(8, PressureMode.ORANGE) == 4
    assert paid_lane_ceiling(8, PressureMode.RED) == 1
    assert paid_lane_ceiling(8, PressureMode.HARD_STOP) == 0


def test_agent_router_hard_cost_contract_excludes_known_expensive_candidate():
    capability = CapabilitySpec(capability_id="code_generation", description="code")
    provider = ProviderSpec(
        provider_id="provider:test",
        display_name="Test",
        adapter_id="adapter:test",
        execution_mode=ExecutionMode.HOSTED_API,
        capabilities=("code_generation",),
    )
    model = ModelSpec(
        model_id="model:test",
        provider_id="provider:test",
        provider_model_name="test-model",
        version="1",
        capabilities=("code_generation",),
        qualification=QualificationState.QUALIFIED,
    )
    agent = AgentSpec(
        agent_id="agent:test",
        model_id="model:test",
        capabilities=("code_generation",),
        qualification=QualificationState.QUALIFIED,
    )
    policy = CapabilityRoutePolicy(
        capability_id="code_generation", preferred_provider_ids=("provider:test",)
    )
    from project_pipeline.domain.agents import router_identifier

    registry = AgentRegistrySnapshot(
        registry_id=router_identifier("REG", "budget-test"),
        capabilities=(capability,),
        providers=(provider,),
        models=(model,),
        agents=(agent,),
        tools=(),
        routing_policies=(policy,),
        generated_at_utc=NOW,
    )
    perf = PerformanceObservation(
        observation_id="PERF-00000000000000000000",
        target_id="agent:test",
        capability_id="code_generation",
        task_class="code",
        success=True,
        latency_ms=10,
        cost_microunits=2000,
        quality_milli=900,
        observed_at_utc=NOW,
    )
    request = ExecutionTaskContract(
        task_id="PP-TASK-000001",
        task_class="code",
        required_capabilities=("code_generation",),
        instructions="write code",
        maximum_cost_microunits=1000,
    )
    decision = AgentRouter().route(
        request,
        registry,
        (
            ProviderStateObservation(
                provider_id="provider:test", state=ProviderRuntimeState.HEALTHY, observed_at_utc=NOW
            ),
        ),
        (CircuitBreakerRecord(provider_id="provider:test", updated_at_utc=NOW),),
        (perf,),
        now=NOW,
    )
    assert decision.selected_provider_id is None
    assert "estimated_cost_above_contract_limit" in decision.candidates[0].reasons
