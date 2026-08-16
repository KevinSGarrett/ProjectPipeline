from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from project_pipeline.agent_router.adapters import ProviderAdapter, ProviderAdapterError
from project_pipeline.agent_router.circuit import record_failure, record_success
from project_pipeline.agent_router.router import AgentRouter
from project_pipeline.domain.agents import (
    AgentRegistrySnapshot,
    CircuitBreakerRecord,
    ExecutionAttempt,
    ExecutionReceipt,
    ExecutionTaskContract,
    PerformanceObservation,
    ProviderStateObservation,
    router_identifier,
)


class AgentRoutingError(RuntimeError):
    """Raised when no qualified provider route can execute a task."""


class AgentRouterService:
    def __init__(
        self,
        registry: AgentRegistrySnapshot,
        adapters: Mapping[str, ProviderAdapter],
        *,
        router: AgentRouter | None = None,
        store: Any | None = None,
    ) -> None:
        self.registry = registry
        self.adapters = dict(adapters)
        self.router = router or AgentRouter()
        self.store = store

    def execute(
        self,
        contract: ExecutionTaskContract,
        provider_states: list[ProviderStateObservation],
        circuits: list[CircuitBreakerRecord],
        performance: list[PerformanceObservation] | None = None,
        *,
        now: datetime | None = None,
    ) -> ExecutionReceipt:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        decision = self.router.route(
            contract, self.registry, provider_states, circuits, performance or [], now=now
        )
        if self.store:
            self.store.save_routing_decision(decision)
        if not decision.selected_provider_id:
            raise AgentRoutingError("no eligible route: " + ",".join(decision.no_route_reasons))
        circuit_by = {x.provider_id: x for x in circuits}
        model_by = {x.model_id: x for x in self.registry.models}
        attempts: list[ExecutionAttempt] = []
        result = None
        # Try eligible candidates in routing order; each fallback preserves the universal task contract.
        for candidate in (c for c in decision.candidates if c.eligible):
            adapter = self.adapters.get(candidate.adapter_id)
            if adapter is None:
                continue
            start = now
            try:
                invocation = adapter.execute(
                    contract, model_name=model_by[candidate.model_id].provider_model_name
                )
                finish = datetime.now(UTC)
                attempts.append(
                    ExecutionAttempt(
                        attempt_id=router_identifier(
                            "ATTEMPT",
                            decision.decision_id,
                            candidate.provider_id,
                            str(len(attempts)),
                        ),
                        provider_id=candidate.provider_id,
                        model_id=candidate.model_id,
                        agent_id=candidate.agent_id,
                        succeeded=True,
                        result=invocation,
                        started_at_utc=start,
                        finished_at_utc=finish,
                    )
                )
                record = circuit_by.get(candidate.provider_id) or CircuitBreakerRecord(
                    provider_id=candidate.provider_id, updated_at_utc=start
                )
                record = record_success(record, finish)
                if self.store:
                    self.store.save_circuit(record)
                result = invocation
                break
            except ProviderAdapterError as error:
                finish = datetime.now(UTC)
                attempts.append(
                    ExecutionAttempt(
                        attempt_id=router_identifier(
                            "ATTEMPT",
                            decision.decision_id,
                            candidate.provider_id,
                            str(len(attempts)),
                        ),
                        provider_id=candidate.provider_id,
                        model_id=candidate.model_id,
                        agent_id=candidate.agent_id,
                        succeeded=False,
                        retryable=error.retryable,
                        error_kind=error.kind,
                        error_message=str(error),
                        started_at_utc=start,
                        finished_at_utc=finish,
                    )
                )
                record = circuit_by.get(candidate.provider_id) or CircuitBreakerRecord(
                    provider_id=candidate.provider_id, updated_at_utc=start
                )
                record = record_failure(record, self.router.circuit_policy, finish, error.kind)
                circuit_by[candidate.provider_id] = record
                if self.store:
                    self.store.save_circuit(record)
                continue
        receipt = ExecutionReceipt(
            receipt_id=router_identifier("ATTEMPT", decision.decision_id, "receipt"),
            task_id=contract.task_id,
            routing_decision_id=decision.decision_id,
            attempts=tuple(attempts),
            succeeded=result is not None,
            result=result,
            generated_at_utc=datetime.now(UTC),
        )
        if self.store:
            self.store.save_execution_receipt(receipt)
        return receipt
