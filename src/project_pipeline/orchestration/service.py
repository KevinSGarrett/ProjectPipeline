from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from project_pipeline.domain.orchestration import (
    DurableBackendKind,
    DurableOperation,
    DurableOperationState,
    WorkflowInstance,
    WorkflowStartRequest,
    WorkflowState,
    canonical_payload_sha256,
    orchestration_identifier,
)
from project_pipeline.orchestration.adapters import (
    BackendUnavailableError,
    BackendUnknownOutcomeError,
)
from project_pipeline.orchestration.persistence import OrchestrationStore
from project_pipeline.orchestration.ports import DurableExecutionPort
from project_pipeline.orchestration.runtime import LocalDurableRuntime


class OrchestrationService:
    """Coordinates canonical local durability state with optional external durable engines."""

    def __init__(
        self,
        store: OrchestrationStore,
        runtime: LocalDurableRuntime,
        backends: Mapping[DurableBackendKind, DurableExecutionPort] | None = None,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.backends = dict(backends or {})

    @staticmethod
    def _now(value: datetime | None = None) -> datetime:
        return (value or datetime.now(UTC)).astimezone(UTC)

    def start(
        self,
        request: WorkflowStartRequest,
        *,
        workflow_name: str,
        now: datetime | None = None,
    ) -> WorkflowInstance:
        current = self._now(now)
        workflow = self.runtime.start(request, now=current)
        if request.backend == DurableBackendKind.LOCAL_REFERENCE:
            return workflow
        if workflow.backend_run_id:
            return workflow
        adapter = self.backends.get(request.backend)
        if adapter is None:
            return self._mark_backend_unavailable(
                workflow.workflow_id, "no configured backend adapter", current
            )
        payload = {
            "workflow_name": workflow_name,
            "definition_id": request.definition_id,
            "input_payload": request.input_payload,
        }
        operation = DurableOperation(
            operation_id=orchestration_identifier(
                "operation", workflow.workflow_id, "START_WORKFLOW", request.idempotency_key
            ),
            workflow_id=workflow.workflow_id,
            operation_type="START_WORKFLOW",
            idempotency_key=request.idempotency_key,
            state=DurableOperationState.PENDING,
            payload=payload,
            payload_sha256=canonical_payload_sha256(payload),
            backend=request.backend,
            created_at_utc=current,
            updated_at_utc=current,
        )
        existing = self.store.get_operation(operation.operation_id)
        if existing is not None:
            if existing.state in {
                DurableOperationState.ACKNOWLEDGED,
                DurableOperationState.RECONCILED,
                DurableOperationState.UNKNOWN_OUTCOME,
            }:
                return self.runtime.query(workflow.workflow_id)
            operation = existing
        else:
            self.store.save_operation(operation)
        sent = operation.model_copy(
            update={
                "state": DurableOperationState.SENT,
                "attempt_count": operation.attempt_count + 1,
                "updated_at_utc": current,
            }
        )
        self.store.save_operation(sent)
        try:
            receipt = adapter.start(request, workflow_name=workflow_name)
        except BackendUnknownOutcomeError as error:
            unknown = sent.model_copy(
                update={
                    "state": DurableOperationState.UNKNOWN_OUTCOME,
                    "last_error": str(error),
                    "updated_at_utc": current,
                }
            )
            self.store.save_operation(unknown)
            return self._mark_recovery_required(
                workflow.workflow_id,
                "REMOTE_START_OUTCOME_UNKNOWN",
                str(error),
                current,
            )
        except BackendUnavailableError as error:
            failed = sent.model_copy(
                update={
                    "state": DurableOperationState.FAILED,
                    "last_error": str(error),
                    "updated_at_utc": current,
                }
            )
            self.store.save_operation(failed)
            return self._mark_backend_unavailable(workflow.workflow_id, str(error), current)
        acknowledged = sent.model_copy(
            update={
                "state": DurableOperationState.ACKNOWLEDGED,
                "backend_operation_id": receipt.backend_operation_id,
                "last_error": None,
                "updated_at_utc": current,
            }
        )
        self.store.save_operation(acknowledged)
        refreshed = self.runtime.query(workflow.workflow_id)
        updated = refreshed.model_copy(
            update={
                "version": refreshed.version + 1,
                "backend_run_id": receipt.backend_run_id,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=refreshed.version)
        self.runtime._event(
            workflow.workflow_id,
            "BACKEND_START_ACKNOWLEDGED",
            now=current,
            payload={
                "backend": request.backend.value,
                "backend_run_id": receipt.backend_run_id,
                "operation_id": acknowledged.operation_id,
            },
        )
        return updated

    def _mark_recovery_required(
        self,
        workflow_id: str,
        code: str,
        message: str,
        now: datetime,
    ) -> WorkflowInstance:
        workflow = self.runtime.query(workflow_id)
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.RECOVERY_REQUIRED,
                "version": workflow.version + 1,
                "assigned_worker_id": None,
                "failure_code": code,
                "failure_message": message,
                "updated_at_utc": now,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self.runtime._event(workflow_id, "RECOVERY_REQUIRED", now=now, payload={"code": code})
        return updated

    def _mark_backend_unavailable(
        self, workflow_id: str, detail: str, now: datetime
    ) -> WorkflowInstance:
        workflow = self.runtime.query(workflow_id)
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.SUSPENDED,
                "version": workflow.version + 1,
                "assigned_worker_id": None,
                "failure_code": "BACKEND_UNAVAILABLE",
                "failure_message": detail,
                "updated_at_utc": now,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self.runtime._event(
            workflow_id,
            "BACKEND_UNAVAILABLE",
            now=now,
            payload={"backend": workflow.backend.value, "detail": detail},
        )
        return updated


class FailoverPlanner:
    """Prevents silent migration of active durable histories between engines."""

    @staticmethod
    def can_failover(workflow: WorkflowInstance, target: DurableBackendKind) -> tuple[bool, str]:
        if workflow.backend == target:
            return False, "target backend is already selected"
        if workflow.backend_run_id:
            return False, "active/existing backend history cannot be silently migrated"
        if workflow.state not in {WorkflowState.SUSPENDED, WorkflowState.PENDING}:
            return (
                False,
                f"workflow state {workflow.state.value} is not eligible for backend failover",
            )
        return True, "workflow has no external run identity; explicit fallback may be planned"
