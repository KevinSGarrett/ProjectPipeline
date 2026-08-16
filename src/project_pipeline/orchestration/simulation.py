from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_pipeline.domain.orchestration import (
    DurableBackendKind,
    OrchestrationSimulationResult,
    WorkflowDefinition,
    WorkflowSignal,
    WorkflowStartRequest,
    WorkflowState,
    WorkflowStepDefinition,
    orchestration_identifier,
)
from project_pipeline.orchestration.adapters import MockDurableBackend
from project_pipeline.orchestration.persistence import OrchestrationStore
from project_pipeline.orchestration.recovery import RecoveryManager
from project_pipeline.orchestration.runtime import LocalDurableRuntime
from project_pipeline.orchestration.service import OrchestrationService


def _definition(name: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        definition_id=orchestration_identifier("workflow_definition", name, "1"),
        workflow_name=name,
        version="1",
        steps=(WorkflowStepDefinition(step_id="execute", name="Execute"),),
    )


def simulate_scenario(root: Path, scenario: str) -> OrchestrationSimulationResult:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    with OrchestrationStore(":memory:", root) as store:
        runtime = LocalDurableRuntime(store)
        definition = _definition(f"simulation-{scenario}")
        runtime.register_definition(definition)
        observations: list[str] = []
        if scenario == "normal":
            workflow = runtime.start(
                WorkflowStartRequest(
                    definition_id=definition.definition_id, idempotency_key="normal"
                ),
                now=now,
            )
            workflow = runtime.complete_step(workflow.workflow_id, now=now + timedelta(seconds=1))
            observations.append("workflow completed exactly once")
        elif scenario == "signal-wait":
            workflow = runtime.start(
                WorkflowStartRequest(
                    definition_id=definition.definition_id, idempotency_key="signal"
                ),
                now=now,
            )
            runtime.wait_for_signal(workflow.workflow_id, "resume", now=now)
            signal = WorkflowSignal(
                signal_id=orchestration_identifier("signal", workflow.workflow_id, "resume", "s1"),
                workflow_id=workflow.workflow_id,
                signal_name="resume",
                idempotency_key="s1",
                observed_at_utc=now + timedelta(seconds=1),
            )
            workflow = runtime.signal(signal)
            observations.append("durable signal wait resumed after persisted inbox delivery")
        elif scenario == "worker-loss":
            workflow = runtime.start(
                WorkflowStartRequest(
                    definition_id=definition.definition_id, idempotency_key="worker"
                ),
                now=now,
            )
            runtime.heartbeat("sim-worker", fencing_epoch=1, ttl_seconds=5, now=now)
            runtime.assign_worker(workflow.workflow_id, "sim-worker", fencing_epoch=1, now=now)
            RecoveryManager(store, runtime).recover_stale_workers(now=now + timedelta(seconds=6))
            workflow = runtime.query(workflow.workflow_id)
            observations.append("expired worker heartbeat produced a bounded retry decision")
        elif scenario == "unknown-outcome":
            backend = MockDurableBackend()
            backend.lose_next_start_response = True
            service = OrchestrationService(store, runtime, {DurableBackendKind.MOCK: backend})
            workflow = service.start(
                WorkflowStartRequest(
                    definition_id=definition.definition_id,
                    idempotency_key="unknown",
                    backend=DurableBackendKind.MOCK,
                ),
                workflow_name=definition.workflow_name,
                now=now,
            )
            RecoveryManager(store, runtime).unknown_outcome_decisions(now=now)
            observations.append("lost backend acknowledgement was not blindly retried")
        else:
            raise ValueError(f"unknown orchestration simulation scenario: {scenario}")
        expected = {
            "normal": WorkflowState.SUCCEEDED,
            "signal-wait": WorkflowState.RUNNING,
            "worker-loss": WorkflowState.RETRY_SCHEDULED,
            "unknown-outcome": WorkflowState.RECOVERY_REQUIRED,
        }[scenario]
        return OrchestrationSimulationResult(
            scenario=scenario,
            passed=workflow.state == expected,
            observations=tuple(observations),
            final_state=workflow.state.value,
        )


def supported_scenarios() -> tuple[str, ...]:
    return ("normal", "signal-wait", "worker-loss", "unknown-outcome")
