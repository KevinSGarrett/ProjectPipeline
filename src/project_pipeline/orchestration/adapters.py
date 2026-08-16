from __future__ import annotations

import importlib.util
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from project_pipeline.domain.orchestration import (
    BackendCapabilities,
    BackendMutationReceipt,
    BackendQualificationState,
    BackendRunObservation,
    DurableBackendKind,
    WorkflowSignal,
    WorkflowStartRequest,
)


class BackendUnavailableError(RuntimeError):
    """Raised when an optional durable backend is not installed or configured."""


class BackendUnknownOutcomeError(RuntimeError):
    """Raised when a backend may have accepted a mutation but its response was lost."""


class HatchetSdkBridge:
    """Thin bridge over Hatchet's workflow runnable API at the qualified source boundary."""

    def __init__(
        self,
        workflow_resolver: Callable[[str], Any],
        *,
        run_observer: Callable[[str], BackendRunObservation] | None = None,
        run_signaler: Callable[[str, WorkflowSignal], BackendMutationReceipt] | None = None,
        run_canceller: Callable[[str, str], BackendMutationReceipt] | None = None,
    ) -> None:
        self.workflow_resolver = workflow_resolver
        self.run_observer = run_observer
        self.run_signaler = run_signaler
        self.run_canceller = run_canceller

    def start(self, workflow_name: str, request: WorkflowStartRequest) -> BackendMutationReceipt:
        workflow = self.workflow_resolver(workflow_name)
        ref = workflow.run(
            request.input_payload,
            wait_for_result=False,
            additional_metadata={
                "project_pipeline_idempotency_key": request.idempotency_key,
                "project_pipeline_definition_id": request.definition_id,
            },
        )
        run_id = str(getattr(ref, "workflow_run_id", ref))
        if not run_id:
            raise BackendUnknownOutcomeError("Hatchet returned no workflow run identity")
        return BackendMutationReceipt(
            backend=DurableBackendKind.HATCHET,
            accepted=True,
            backend_operation_id=run_id,
            backend_run_id=run_id,
            detail="Hatchet workflow accepted through run(wait_for_result=False)",
        )

    def observe(self, backend_run_id: str) -> BackendRunObservation:
        if self.run_observer is None:
            raise BackendUnavailableError("Hatchet run observation bridge is not configured")
        return self.run_observer(backend_run_id)

    def signal(self, backend_run_id: str, signal: WorkflowSignal) -> BackendMutationReceipt:
        if self.run_signaler is None:
            raise BackendUnavailableError("Hatchet signal bridge is not configured")
        return self.run_signaler(backend_run_id, signal)

    def cancel(self, backend_run_id: str, idempotency_key: str) -> BackendMutationReceipt:
        if self.run_canceller is None:
            raise BackendUnavailableError("Hatchet cancellation bridge is not configured")
        return self.run_canceller(backend_run_id, idempotency_key)


class HatchetDurableAdapter:
    def __init__(self, bridge: HatchetSdkBridge | None = None) -> None:
        self.bridge = bridge

    def capabilities(self) -> BackendCapabilities:
        installed = importlib.util.find_spec("hatchet_sdk") is not None
        if self.bridge is not None:
            qualification = BackendQualificationState.ADAPTER_IMPLEMENTED
            detail = (
                "Hatchet adapter bridge configured; live backend qualification remains separate"
            )
        elif not installed:
            qualification = BackendQualificationState.DEPENDENCY_UNAVAILABLE
            detail = "hatchet_sdk is not installed in the current environment"
        else:
            qualification = BackendQualificationState.CONFIGURATION_REQUIRED
            detail = "hatchet_sdk is installed but no Project Pipeline bridge/runtime is configured"
        return BackendCapabilities(
            backend=DurableBackendKind.HATCHET,
            supports_signals=True,
            supports_timers=True,
            supports_retries=True,
            supports_cancel=True,
            supports_query=True,
            supports_native_recovery=True,
            qualification=qualification,
            detail=detail,
        )

    def _bridge(self) -> HatchetSdkBridge:
        if self.bridge is None:
            raise BackendUnavailableError(self.capabilities().detail)
        return self.bridge

    def start(self, request: WorkflowStartRequest, *, workflow_name: str) -> BackendMutationReceipt:
        return self._bridge().start(workflow_name, request)

    def observe(self, backend_run_id: str) -> BackendRunObservation:
        return self._bridge().observe(backend_run_id)

    def signal(self, backend_run_id: str, signal: WorkflowSignal) -> BackendMutationReceipt:
        return self._bridge().signal(backend_run_id, signal)

    def cancel(self, backend_run_id: str, *, idempotency_key: str) -> BackendMutationReceipt:
        return self._bridge().cancel(backend_run_id, idempotency_key)


class _FallbackAdapter:
    backend: DurableBackendKind
    module_name: str
    label: str

    def capabilities(self) -> BackendCapabilities:
        installed = importlib.util.find_spec(self.module_name) is not None
        qualification = (
            BackendQualificationState.CONFIGURATION_REQUIRED
            if installed
            else BackendQualificationState.DEPENDENCY_UNAVAILABLE
        )
        return BackendCapabilities(
            backend=self.backend,
            supports_signals=True,
            supports_timers=True,
            supports_retries=True,
            supports_cancel=True,
            supports_query=True,
            supports_native_recovery=True,
            qualification=qualification,
            detail=(
                f"{self.label} dependency detected; fallback requires separate live qualification"
                if installed
                else f"{self.label} dependency is unavailable; adapter remains a conformance target"
            ),
        )

    def start(self, request: WorkflowStartRequest, *, workflow_name: str) -> BackendMutationReceipt:
        raise BackendUnavailableError(self.capabilities().detail)

    def observe(self, backend_run_id: str) -> BackendRunObservation:
        raise BackendUnavailableError(self.capabilities().detail)

    def signal(self, backend_run_id: str, signal: WorkflowSignal) -> BackendMutationReceipt:
        raise BackendUnavailableError(self.capabilities().detail)

    def cancel(self, backend_run_id: str, *, idempotency_key: str) -> BackendMutationReceipt:
        raise BackendUnavailableError(self.capabilities().detail)


class DBOSFallbackAdapter(_FallbackAdapter):
    backend = DurableBackendKind.DBOS
    module_name = "dbos"
    label = "DBOS"


class TemporalFallbackAdapter(_FallbackAdapter):
    backend = DurableBackendKind.TEMPORAL
    module_name = "temporalio"
    label = "Temporal"


class MockDurableBackend:
    """Deterministic backend used to test retries, lost acknowledgements and reconciliation."""

    def __init__(self) -> None:
        self.runs: dict[str, str] = {}
        self.mutation_keys: dict[str, BackendMutationReceipt] = {}
        self.fail_next_start = False
        self.lose_next_start_response = False
        self.start_calls = 0

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend=DurableBackendKind.MOCK,
            supports_signals=True,
            supports_timers=True,
            supports_retries=True,
            supports_cancel=True,
            supports_query=True,
            supports_native_recovery=False,
            qualification=BackendQualificationState.LOCAL_VERIFIED,
            detail="deterministic test backend",
        )

    def start(self, request: WorkflowStartRequest, *, workflow_name: str) -> BackendMutationReceipt:
        self.start_calls += 1
        key = f"start:{request.definition_id}:{request.idempotency_key}"
        if key in self.mutation_keys:
            return self.mutation_keys[key]
        if self.fail_next_start:
            self.fail_next_start = False
            raise BackendUnavailableError("simulated backend outage")
        run_id = f"mock-{request.definition_id[-12:].lower()}-{len(self.runs) + 1}"
        receipt = BackendMutationReceipt(
            backend=DurableBackendKind.MOCK,
            accepted=True,
            backend_operation_id=run_id,
            backend_run_id=run_id,
            detail=f"accepted {workflow_name}",
        )
        self.runs[run_id] = "RUNNING"
        self.mutation_keys[key] = receipt
        if self.lose_next_start_response:
            self.lose_next_start_response = False
            raise BackendUnknownOutcomeError("simulated response loss after remote acceptance")
        return receipt

    def observe(self, backend_run_id: str) -> BackendRunObservation:
        state = self.runs.get(backend_run_id)
        if state is None:
            raise KeyError(f"unknown mock backend run: {backend_run_id}")
        return BackendRunObservation(
            backend=DurableBackendKind.MOCK,
            backend_run_id=backend_run_id,
            state=state,
            observed_at_utc=datetime.now(UTC),
        )

    def signal(self, backend_run_id: str, signal: WorkflowSignal) -> BackendMutationReceipt:
        if backend_run_id not in self.runs:
            raise KeyError(f"unknown mock backend run: {backend_run_id}")
        key = f"signal:{backend_run_id}:{signal.idempotency_key}"
        receipt = self.mutation_keys.get(key)
        if receipt is None:
            receipt = BackendMutationReceipt(
                backend=DurableBackendKind.MOCK,
                accepted=True,
                backend_operation_id=key,
                backend_run_id=backend_run_id,
                detail=f"accepted signal {signal.signal_name}",
            )
            self.mutation_keys[key] = receipt
        return receipt

    def cancel(self, backend_run_id: str, *, idempotency_key: str) -> BackendMutationReceipt:
        if backend_run_id not in self.runs:
            raise KeyError(f"unknown mock backend run: {backend_run_id}")
        key = f"cancel:{backend_run_id}:{idempotency_key}"
        receipt = self.mutation_keys.get(key)
        if receipt is None:
            self.runs[backend_run_id] = "CANCELLED"
            receipt = BackendMutationReceipt(
                backend=DurableBackendKind.MOCK,
                accepted=True,
                backend_operation_id=key,
                backend_run_id=backend_run_id,
                detail="cancelled",
            )
            self.mutation_keys[key] = receipt
        return receipt
