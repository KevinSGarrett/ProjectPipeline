from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from project_pipeline.domain.orchestration import (
    DurableOperation,
    DurableOperationState,
    RecoveryAction,
    RecoveryDecision,
    WorkflowState,
    orchestration_identifier,
)
from project_pipeline.orchestration.persistence import OrchestrationStore
from project_pipeline.orchestration.runtime import LocalDurableRuntime

ReconciliationObservation = Literal["APPLIED", "NOT_APPLIED", "UNKNOWN"]


class RecoveryManager:
    def __init__(self, store: OrchestrationStore, runtime: LocalDurableRuntime) -> None:
        self.store = store
        self.runtime = runtime

    @staticmethod
    def _now(value: datetime | None = None) -> datetime:
        return (value or datetime.now(UTC)).astimezone(UTC)

    def recover_stale_workers(self, *, now: datetime | None = None) -> tuple[RecoveryDecision, ...]:
        current = self._now(now)
        decisions: list[RecoveryDecision] = []
        for worker in self.store.stale_workers(current):
            for workflow in self.store.workflows_for_worker(worker.worker_id):
                if workflow.state != WorkflowState.RUNNING:
                    action = RecoveryAction.MARK_RECOVERY_REQUIRED
                    safe = False
                    reasons = ("WORKER_HEARTBEAT_EXPIRED", f"STATE_{workflow.state.value}")
                else:
                    step = self.runtime.current_step(workflow.workflow_id)
                    if (
                        step is not None
                        and step.recoverable
                        and workflow.current_attempt < step.retry_policy.max_attempts
                    ):
                        action = RecoveryAction.RETRY_STEP
                        safe = True
                        reasons = ("WORKER_HEARTBEAT_EXPIRED", "STEP_RECOVERABLE")
                    else:
                        action = RecoveryAction.MARK_RECOVERY_REQUIRED
                        safe = False
                        reasons = ("WORKER_HEARTBEAT_EXPIRED", "RETRY_NOT_SAFE")
                decision = RecoveryDecision(
                    recovery_id=orchestration_identifier(
                        "recovery",
                        workflow.workflow_id,
                        action.value,
                        "|".join(reasons),
                        worker.worker_id,
                        "",
                    ),
                    workflow_id=workflow.workflow_id,
                    action=action,
                    reason_codes=reasons,
                    created_at_utc=current,
                    worker_id=worker.worker_id,
                    safe_to_automate=safe,
                )
                self.store.save_recovery_decision(decision)
                if action == RecoveryAction.RETRY_STEP:
                    self.runtime.fail_step(
                        workflow.workflow_id,
                        failure_code="WORKER_LOST",
                        failure_message=f"worker heartbeat expired: {worker.worker_id}",
                        retryable=True,
                        now=current,
                    )
                else:
                    refreshed = self.store.get_workflow(workflow.workflow_id)
                    if refreshed is not None and refreshed.state == WorkflowState.RUNNING:
                        updated = refreshed.model_copy(
                            update={
                                "state": WorkflowState.RECOVERY_REQUIRED,
                                "version": refreshed.version + 1,
                                "assigned_worker_id": None,
                                "failure_code": "WORKER_LOST",
                                "failure_message": f"worker heartbeat expired: {worker.worker_id}",
                                "updated_at_utc": current,
                            }
                        )
                        self.store.update_workflow(updated, expected_version=refreshed.version)
                        self.runtime._event(
                            workflow.workflow_id,
                            "RECOVERY_REQUIRED",
                            now=current,
                            payload={"worker_id": worker.worker_id, "reason": "WORKER_LOST"},
                        )
                decisions.append(decision)
        return tuple(decisions)

    def unknown_outcome_decisions(
        self, *, now: datetime | None = None
    ) -> tuple[RecoveryDecision, ...]:
        current = self._now(now)
        decisions: list[RecoveryDecision] = []
        for operation in self.store.operations_by_state(DurableOperationState.UNKNOWN_OUTCOME):
            reasons = ("REMOTE_MUTATION_OUTCOME_UNKNOWN", "BLIND_RETRY_FORBIDDEN")
            decision = RecoveryDecision(
                recovery_id=orchestration_identifier(
                    "recovery",
                    operation.workflow_id,
                    RecoveryAction.RECONCILE_OPERATION.value,
                    "|".join(reasons),
                    "",
                    operation.operation_id,
                ),
                workflow_id=operation.workflow_id,
                action=RecoveryAction.RECONCILE_OPERATION,
                reason_codes=reasons,
                created_at_utc=current,
                operation_id=operation.operation_id,
                safe_to_automate=False,
            )
            self.store.save_recovery_decision(decision)
            decisions.append(decision)
        return tuple(decisions)

    def reconcile_operation(
        self,
        operation_id: str,
        observer: Callable[[str], ReconciliationObservation],
        *,
        now: datetime | None = None,
    ) -> DurableOperation:
        current = self._now(now)
        operation = self.store.get_operation(operation_id)
        if operation is None:
            raise KeyError(f"unknown orchestration operation: {operation_id}")
        if operation.state != DurableOperationState.UNKNOWN_OUTCOME:
            return operation
        observation = observer(operation_id)
        if observation == "UNKNOWN":
            return operation
        if observation == "APPLIED":
            state = DurableOperationState.RECONCILED
            detail = "remote effect observed after uncertain response"
        else:
            state = DurableOperationState.PENDING
            detail = "remote effect absent; operation may be safely reconsidered"
        updated = operation.model_copy(
            update={
                "state": state,
                "updated_at_utc": current,
                "last_error": detail,
            }
        )
        self.store.save_operation(updated)
        return updated
