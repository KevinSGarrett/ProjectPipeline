from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.agent_router.adapters import MockProviderAdapter, ProviderAdapterError
from project_pipeline.agent_router.registry import build_registry
from project_pipeline.agent_router.service import AgentRouterService
from project_pipeline.budget.persistence import BudgetStore
from project_pipeline.budget.service import BudgetGovernor
from project_pipeline.domain.agents import (
    AgentSpec,
    CapabilityRoutePolicy,
    CapabilitySpec,
    CircuitBreakerRecord,
    ExecutionMode,
    ExecutionTaskContract,
    ModelSpec,
    ProviderRuntimeState,
    ProviderSpec,
    ProviderStateObservation,
    QualificationState,
)
from project_pipeline.domain.budget import (
    BudgetAdmissionRequest,
    BudgetLimit,
    BudgetScopeType,
    QuotaLimit,
    budget_identifier,
)
from project_pipeline.domain.orchestration import DurableBackendKind, WorkflowStartRequest
from project_pipeline.domain.verification import FaultScenarioResult, verification_identifier
from project_pipeline.orchestration.adapters import BackendUnavailableError, DBOSFallbackAdapter
from project_pipeline.orchestration.simulation import simulate_scenario as simulate_orchestration


def _agent_fault_fallback(kind: str, provider_state: str, message: str) -> tuple[bool, str]:
    """Inject one provider fault and require deterministic fallback to a healthy local provider."""
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    capability = CapabilitySpec(
        capability_id="fault_reasoning", description="Fault verification capability"
    )
    providers = (
        ProviderSpec(
            provider_id="provider:fault-primary",
            display_name="Fault Primary",
            adapter_id="adapter:fault-primary",
            execution_mode=ExecutionMode.MOCK,
            capabilities=(capability.capability_id,),
        ),
        ProviderSpec(
            provider_id="provider:fault-fallback",
            display_name="Fault Fallback",
            adapter_id="adapter:fault-fallback",
            execution_mode=ExecutionMode.MOCK,
            capabilities=(capability.capability_id,),
            local=True,
        ),
    )
    models = (
        ModelSpec(
            model_id="model:fault-primary",
            provider_id=providers[0].provider_id,
            provider_model_name="primary",
            version="1",
            capabilities=(capability.capability_id,),
            qualification=QualificationState.QUALIFIED,
        ),
        ModelSpec(
            model_id="model:fault-fallback",
            provider_id=providers[1].provider_id,
            provider_model_name="fallback",
            version="1",
            capabilities=(capability.capability_id,),
            qualification=QualificationState.QUALIFIED,
            local=True,
        ),
    )
    agents = (
        AgentSpec(
            agent_id="agent:fault-primary",
            model_id=models[0].model_id,
            capabilities=(capability.capability_id,),
            qualification=QualificationState.QUALIFIED,
        ),
        AgentSpec(
            agent_id="agent:fault-fallback",
            model_id=models[1].model_id,
            capabilities=(capability.capability_id,),
            qualification=QualificationState.QUALIFIED,
        ),
    )
    registry = build_registry(
        capabilities=(capability,),
        providers=providers,
        models=models,
        agents=agents,
        routing_policies=(
            CapabilityRoutePolicy(
                capability_id=capability.capability_id,
                preferred_provider_ids=(providers[0].provider_id,),
                fallback_provider_ids=(providers[1].provider_id,),
            ),
        ),
        when=now,
    )
    primary = MockProviderAdapter(
        providers[0].provider_id,
        [ProviderAdapterError(message, kind=kind, retryable=True, provider_state=provider_state)],
    )
    primary.adapter_id = providers[0].adapter_id
    fallback = MockProviderAdapter(providers[1].provider_id)
    fallback.adapter_id = providers[1].adapter_id
    states = [
        ProviderStateObservation(
            provider_id=provider.provider_id,
            state=ProviderRuntimeState.HEALTHY,
            observed_at_utc=now,
        )
        for provider in providers
    ]
    contract = ExecutionTaskContract(
        task_id=f"FAULT-{kind}",
        task_class="fault-verification",
        required_capabilities=(capability.capability_id,),
        instructions="Verify provider fault fallback",
    )
    receipt = AgentRouterService(
        registry,
        {primary.adapter_id: primary, fallback.adapter_id: fallback},
    ).execute(
        contract,
        states,
        [CircuitBreakerRecord(provider_id=providers[0].provider_id, updated_at_utc=now)],
    )
    sequence = ",".join(attempt.provider_id for attempt in receipt.attempts)
    passed = (
        receipt.succeeded
        and len(receipt.attempts) == 2
        and receipt.attempts[-1].provider_id == providers[1].provider_id
    )
    return (
        passed,
        f"succeeded={receipt.succeeded}; attempts={sequence}; first_error={receipt.attempts[0].error_kind}",
    )


def _quota_exhaustion(root: Path) -> tuple[bool, str]:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory(prefix="project-pipeline-fault-quota-") as temp:  # noqa: SIM117 - inner store depends on temp
        with BudgetStore(Path(temp) / "budget.sqlite", root) as store:
            governor = BudgetGovernor(store)
            governor.configure_limit(
                BudgetLimit(
                    limit_id=budget_identifier("LIMIT", "GLOBAL:*", "fault-cycle"),
                    scope_type=BudgetScopeType.GLOBAL,
                    scope_id="*",
                    cycle_id="fault-cycle",
                    hard_cap_microunits=1_000_000,
                    soft_cap_microunits=1_000_000,
                    protected_reserve_microunits=0,
                )
            )
            quota_id = budget_identifier(
                "QUOTA", "PROJECT:PROJECT-PIPELINE", "provider:fault", "requests"
            )
            governor.configure_quota(
                QuotaLimit(
                    quota_id=quota_id,
                    scope_key="PROJECT:PROJECT-PIPELINE",
                    provider_id="provider:fault",
                    quota_name="requests",
                    capacity_units=10,
                    protected_units=0,
                )
            )
            request = BudgetAdmissionRequest(
                project_id="PROJECT-PIPELINE",
                task_id="FAULT-QUOTA",
                task_class="fault-verification",
                provider_id="provider:fault",
                scope_keys=("GLOBAL:*",),
                estimated_p50_microunits=0,
                estimated_p90_microunits=0,
                quota_requirements={quota_id: 11},
                paid_incremental=False,
            )
            decision = governor.admit(request, cycle_id="fault-cycle", now=now)
            passed = not decision.admitted and any(
                reason.startswith("quota_insufficient:") for reason in decision.reasons
            )
            return passed, f"admitted={decision.admitted}; reasons={','.join(decision.reasons)}"


def _dependency_failure() -> tuple[bool, str]:
    adapter = DBOSFallbackAdapter()
    request = WorkflowStartRequest(
        definition_id="WFDEF-AAAAAAAAAAAAAAAAAAAA",
        idempotency_key="fault-dependency",
        backend=DurableBackendKind.DBOS,
    )
    try:
        adapter.start(request, workflow_name="fault-dependency")
    except BackendUnavailableError as exc:
        return True, f"fallback refused unqualified dependency: {exc}"
    return False, "unqualified fallback unexpectedly accepted execution"


def run_fault_scenarios(root: Path) -> tuple[FaultScenarioResult, ...]:
    unknown = simulate_orchestration(root, "unknown-outcome")
    worker = simulate_orchestration(root, "worker-loss")
    provider_passed, provider_observed = _agent_fault_fallback(
        "HTTP_ERROR", "UNAVAILABLE", "simulated provider error"
    )
    latency_passed, latency_observed = _agent_fault_fallback(
        "TIMEOUT", "DEGRADED", "simulated provider latency timeout"
    )
    network_passed, network_observed = _agent_fault_fallback(
        "NETWORK_LOSS", "UNAVAILABLE", "simulated network loss"
    )
    quota_passed, quota_observed = _quota_exhaustion(root)
    dependency_passed, dependency_observed = _dependency_failure()

    return (
        FaultScenarioResult(
            fault_id=verification_identifier("FAULT", "provider-error", provider_observed),
            scenario="provider-error",
            injected_fault="Preferred provider returns a retryable provider error",
            expected_behavior="Router records the failed attempt and falls back to a qualified healthy provider",
            observed_behavior=provider_observed,
            passed=provider_passed,
        ),
        FaultScenarioResult(
            fault_id=verification_identifier("FAULT", "provider-latency-timeout", latency_observed),
            scenario="provider-latency-timeout",
            injected_fault="Preferred provider exceeds the execution timeout",
            expected_behavior="Timeout is explicit and qualified fallback work can continue",
            observed_behavior=latency_observed,
            passed=latency_passed,
        ),
        FaultScenarioResult(
            fault_id=verification_identifier("FAULT", "network-loss", network_observed),
            scenario="network-loss",
            injected_fault="Preferred provider transport loses network connectivity",
            expected_behavior="Network loss is visible and a qualified fallback provider can continue",
            observed_behavior=network_observed,
            passed=network_passed,
        ),
        FaultScenarioResult(
            fault_id=verification_identifier(
                "FAULT", "lost-backend-acknowledgement", unknown.final_state
            ),
            scenario="lost-backend-acknowledgement",
            injected_fault="Backend accepts start but acknowledgement is lost",
            expected_behavior="Workflow enters RECOVERY_REQUIRED and is not blindly retried",
            observed_behavior=f"final_state={unknown.final_state}; {'; '.join(unknown.observations)}",
            passed=unknown.passed and unknown.final_state == "RECOVERY_REQUIRED",
        ),
        FaultScenarioResult(
            fault_id=verification_identifier("FAULT", "worker-termination", worker.final_state),
            scenario="worker-termination",
            injected_fault="Assigned worker heartbeat expires after worker termination",
            expected_behavior="Recoverable work receives a bounded retry decision",
            observed_behavior=f"final_state={worker.final_state}; {'; '.join(worker.observations)}",
            passed=worker.passed and worker.final_state == "RETRY_SCHEDULED",
        ),
        FaultScenarioResult(
            fault_id=verification_identifier("FAULT", "quota-exhaustion", quota_observed),
            scenario="quota-exhaustion",
            injected_fault="Requested provider quota exceeds the remaining configured quota",
            expected_behavior="Budget Governor rejects admission rather than exceeding quota",
            observed_behavior=quota_observed,
            passed=quota_passed,
        ),
        FaultScenarioResult(
            fault_id=verification_identifier("FAULT", "dependency-failure", dependency_observed),
            scenario="dependency-failure",
            injected_fault="Optional durable fallback dependency is unavailable or unqualified",
            expected_behavior="Fallback adapter fails closed instead of executing through an unqualified dependency",
            observed_behavior=dependency_observed,
            passed=dependency_passed,
        ),
    )
