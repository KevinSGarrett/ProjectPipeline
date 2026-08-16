from __future__ import annotations

from typing import Protocol

from project_pipeline.domain.orchestration import (
    BackendCapabilities,
    BackendMutationReceipt,
    BackendRunObservation,
    WorkflowSignal,
    WorkflowStartRequest,
)


class DurableExecutionPort(Protocol):
    def capabilities(self) -> BackendCapabilities: ...

    def start(
        self, request: WorkflowStartRequest, *, workflow_name: str
    ) -> BackendMutationReceipt: ...

    def observe(self, backend_run_id: str) -> BackendRunObservation: ...

    def signal(self, backend_run_id: str, signal: WorkflowSignal) -> BackendMutationReceipt: ...

    def cancel(self, backend_run_id: str, *, idempotency_key: str) -> BackendMutationReceipt: ...
