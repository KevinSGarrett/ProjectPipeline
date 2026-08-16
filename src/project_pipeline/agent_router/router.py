from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from project_pipeline.agent_router.circuit import normalize_circuit
from project_pipeline.agent_router.performance import summarize_performance
from project_pipeline.domain.agents import (
    AgentRegistrySnapshot,
    CircuitBreakerPolicy,
    CircuitBreakerRecord,
    ExecutionTaskContract,
    PerformanceObservation,
    ProviderRuntimeState,
    ProviderStateObservation,
    QualificationState,
    RouteCandidate,
    RoutingDecision,
    agent_fingerprint,
    router_identifier,
)

_ALLOWED_NORMAL = {ProviderRuntimeState.HEALTHY}
_ALLOWED_DEGRADED = {
    ProviderRuntimeState.DEGRADED,
    ProviderRuntimeState.QUOTA_LOW,
    ProviderRuntimeState.RECOVERING,
}


class AgentRouter:
    """Capability-first deterministic router. Provider choice is subordinate to eligibility."""

    def __init__(self, circuit_policy: CircuitBreakerPolicy | None = None) -> None:
        self.circuit_policy = circuit_policy or CircuitBreakerPolicy()

    def route(
        self,
        request: ExecutionTaskContract,
        registry: AgentRegistrySnapshot,
        provider_states: Iterable[ProviderStateObservation],
        circuit_records: Iterable[CircuitBreakerRecord],
        performance: Iterable[PerformanceObservation] = (),
        *,
        now: datetime | None = None,
    ) -> RoutingDecision:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        states = {item.provider_id: item for item in provider_states}
        circuits = {
            item.provider_id: normalize_circuit(item, self.circuit_policy, now)
            for item in circuit_records
        }
        perf = summarize_performance(performance)
        providers = {item.provider_id: item for item in registry.providers}
        models = {item.model_id: item for item in registry.models}
        policies = {item.capability_id: item for item in registry.routing_policies}
        primary_policy = (
            policies.get(request.required_capabilities[0])
            if request.required_capabilities
            else None
        )
        order = (
            tuple(primary_policy.preferred_provider_ids + primary_policy.fallback_provider_ids)
            if primary_policy
            else ()
        )
        order_index = {provider_id: index for index, provider_id in enumerate(order)}
        candidates = []
        required = set(request.required_capabilities)
        for agent in registry.agents:
            model = models.get(agent.model_id)
            if model is None:
                continue
            provider = providers.get(model.provider_id)
            if provider is None:
                continue
            reasons = []
            if (
                not required <= set(agent.capabilities)
                or not required <= set(model.capabilities)
                or not required <= set(provider.capabilities)
            ):
                continue  # capability-first: non-capable targets are not provider candidates at all
            if not provider.enabled:
                reasons.append("provider_disabled_by_configuration")
            if not request.allow_data_egress and provider.data_egress:
                reasons.append("data_egress_not_allowed")
            if model.quality_tier != request.quality_tier and request.quality_tier not in {
                "standard",
                "any",
            }:
                reasons.append(f"quality_tier:{model.quality_tier}")
            qualification = min(
                (agent.qualification, model.qualification),
                key=lambda q: [
                    QualificationState.REJECTED,
                    QualificationState.EXPIRED,
                    QualificationState.QUARANTINED,
                    QualificationState.SHADOW,
                    QualificationState.CANARY,
                    QualificationState.QUALIFIED,
                ].index(q),
            )
            if qualification is QualificationState.CANARY:
                if not request.allow_canary:
                    reasons.append(f"qualification:{qualification.value}")
            elif qualification is not QualificationState.QUALIFIED:
                reasons.append(f"qualification:{qualification.value}")
            observation = states.get(provider.provider_id) or ProviderStateObservation(
                provider_id=provider.provider_id,
                state=ProviderRuntimeState.UNAVAILABLE,
                reason="no_runtime_observation",
                observed_at_utc=now,
            )
            allowed = set(_ALLOWED_NORMAL)
            if request.allow_degraded:
                allowed |= _ALLOWED_DEGRADED
            if observation.state not in allowed:
                reasons.append(f"provider_state:{observation.state.value}")
            circuit = circuits.get(provider.provider_id) or CircuitBreakerRecord(
                provider_id=provider.provider_id, updated_at_utc=now
            )
            if not circuit.permits(now, self.circuit_policy):
                reasons.append(f"circuit:{circuit.state.value}")
            rank = order_index.get(provider.provider_id, 5000)
            summaries = [
                perf.get((agent.agent_id, cap)) or perf.get((model.model_id, cap))
                for cap in request.required_capabilities
            ]
            summaries = [x for x in summaries if x is not None]
            perf_summary = summaries[0] if summaries else None
            if (
                request.maximum_cost_microunits is not None
                and perf_summary is not None
                and perf_summary.mean_cost_microunits is not None
                and perf_summary.mean_cost_microunits > request.maximum_cost_microunits
            ):
                reasons.append("estimated_cost_above_contract_limit")
            score = 100000 - rank * 1000
            if provider.local:
                score += 300
            if observation.state is ProviderRuntimeState.HEALTHY:
                score += 500
            elif observation.state is ProviderRuntimeState.DEGRADED:
                score -= 250
            elif observation.state is ProviderRuntimeState.QUOTA_LOW:
                score -= 500
            if perf_summary:
                score += perf_summary.success_milli + perf_summary.quality_milli
                score -= min(perf_summary.mean_latency_ms // 10, 2000)
                if perf_summary.mean_cost_microunits is not None:
                    score -= min(perf_summary.mean_cost_microunits // 1000, 2000)
            candidates.append(
                RouteCandidate(
                    agent_id=agent.agent_id,
                    model_id=model.model_id,
                    provider_id=provider.provider_id,
                    adapter_id=provider.adapter_id,
                    eligible=not reasons,
                    reasons=tuple(reasons),
                    fallback_rank=rank,
                    score=score,
                    provider_state=observation.state,
                    circuit_state=circuit.state,
                    qualification=qualification,
                    performance=perf_summary,
                )
            )
        candidates = sorted(
            candidates,
            key=lambda c: (
                not c.eligible,
                -c.score,
                c.fallback_rank,
                c.provider_id,
                c.model_id,
                c.agent_id,
            ),
        )
        selected = next((c for c in candidates if c.eligible), None)
        no_route = (
            ()
            if selected
            else (
                ("no_capability_match",)
                if not candidates
                else tuple(sorted({r for c in candidates for r in c.reasons}))
            )
        )
        request_fp = agent_fingerprint(request.model_dump(mode="json"))
        return RoutingDecision(
            decision_id=router_identifier(
                "ROUTE", request.task_id, request_fp, registry.registry_id
            ),
            request_fingerprint=request_fp,
            task_id=request.task_id,
            required_capabilities=request.required_capabilities,
            candidates=tuple(candidates),
            selected_agent_id=selected.agent_id if selected else None,
            selected_model_id=selected.model_id if selected else None,
            selected_provider_id=selected.provider_id if selected else None,
            generated_at_utc=now,
            no_route_reasons=no_route,
        )
