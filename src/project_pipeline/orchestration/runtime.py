from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from project_pipeline.domain.orchestration import (
    DurableWait,
    WaitKind,
    WorkerHeartbeat,
    WorkflowCheckpoint,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowSignal,
    WorkflowStartRequest,
    WorkflowState,
    WorkflowStepDefinition,
    canonical_payload_sha256,
    orchestration_identifier,
)
from project_pipeline.lifecycle import CheckpointDecision
from project_pipeline.orchestration.persistence import OrchestrationStore


class WorkflowStateError(RuntimeError):
    """Raised when an orchestration command is invalid for the current state."""


class LocalDurableRuntime:
    """Deterministic reference runtime for Project Pipeline-owned durability semantics."""

    def __init__(self, store: OrchestrationStore) -> None:
        self.store = store

    @staticmethod
    def _now(value: datetime | None = None) -> datetime:
        return (value or datetime.now(UTC)).astimezone(UTC)

    def register_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        return self.store.register_definition(definition)

    def _event(
        self,
        workflow_id: str,
        event_type: str,
        *,
        now: datetime,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> WorkflowEvent:
        sequence = self.store.next_event_sequence(workflow_id)
        event = WorkflowEvent(
            event_id=orchestration_identifier("event", workflow_id, str(sequence), event_type),
            workflow_id=workflow_id,
            sequence=sequence,
            event_type=event_type,
            occurred_at_utc=now,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        return self.store.append_event(event)

    def start(
        self, request: WorkflowStartRequest, *, now: datetime | None = None
    ) -> WorkflowInstance:
        current = self._now(now)
        definition = self.store.get_definition(request.definition_id)
        if definition is None:
            raise KeyError(f"unknown workflow definition: {request.definition_id}")
        existing = self.store.find_workflow_by_idempotency(
            request.definition_id, request.idempotency_key
        )
        if existing is not None:
            if (
                existing.input_payload != request.input_payload
                or existing.backend != request.backend
            ):
                raise WorkflowStateError(
                    "workflow idempotency key was reused with different input/backend"
                )
            return existing
        workflow_id = orchestration_identifier(
            "workflow", request.definition_id, request.idempotency_key
        )
        workflow = WorkflowInstance(
            workflow_id=workflow_id,
            definition_id=request.definition_id,
            idempotency_key=request.idempotency_key,
            state=WorkflowState.RUNNING,
            version=1,
            backend=request.backend,
            input_payload=request.input_payload,
            current_step_index=0,
            current_attempt=1,
            created_at_utc=current,
            updated_at_utc=current,
        )
        self.store.create_workflow(workflow)
        self._event(
            workflow.workflow_id,
            "WORKFLOW_STARTED",
            now=current,
            payload={"definition_id": definition.definition_id, "backend": request.backend.value},
            correlation_id=request.idempotency_key,
        )
        return workflow

    def query(self, workflow_id: str) -> WorkflowInstance:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(f"unknown workflow: {workflow_id}")
        return workflow

    def current_step(self, workflow_id: str) -> WorkflowStepDefinition | None:
        workflow = self.query(workflow_id)
        definition = self.store.get_definition(workflow.definition_id)
        if definition is None:
            raise KeyError(f"workflow definition disappeared: {workflow.definition_id}")
        if workflow.current_step_index >= len(definition.steps):
            return None
        return definition.steps[workflow.current_step_index]

    def assign_worker(
        self,
        workflow_id: str,
        worker_id: str,
        *,
        fencing_epoch: int,
        now: datetime | None = None,
    ) -> WorkflowInstance:
        current = self._now(now)
        workflow = self.query(workflow_id)
        if workflow.state not in {WorkflowState.RUNNING, WorkflowState.RETRY_SCHEDULED}:
            raise WorkflowStateError(
                f"cannot assign worker while workflow is {workflow.state.value}"
            )
        if workflow.state == WorkflowState.RETRY_SCHEDULED and (
            workflow.retry_available_at_utc is None or workflow.retry_available_at_utc > current
        ):
            raise WorkflowStateError("retry is not due")
        heartbeat = self.store.worker(worker_id)
        if heartbeat is None or heartbeat.expires_at_utc <= current:
            raise WorkflowStateError("worker has no current heartbeat")
        if heartbeat.fencing_epoch != fencing_epoch:
            raise WorkflowStateError("worker fencing epoch mismatch")
        attempt = workflow.current_attempt
        if workflow.state == WorkflowState.RETRY_SCHEDULED:
            attempt += 1
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.RUNNING,
                "version": workflow.version + 1,
                "assigned_worker_id": worker_id,
                "current_attempt": attempt,
                "retry_available_at_utc": None,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(
            workflow_id,
            "STEP_ASSIGNED",
            now=current,
            payload={"worker_id": worker_id, "fencing_epoch": fencing_epoch, "attempt": attempt},
        )
        return updated

    def checkpoint(
        self,
        workflow_id: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> WorkflowCheckpoint:
        current = self._now(now)
        workflow = self.query(workflow_id)
        step = self.current_step(workflow_id)
        if step is None:
            raise WorkflowStateError("completed workflow has no step to checkpoint")
        if workflow.state != WorkflowState.RUNNING:
            raise WorkflowStateError("checkpoints require a RUNNING workflow")
        if {
            "no_additional_action_needed",
            "eligible_unrelated_lanes",
        }.issubset(payload):
            decision = CheckpointDecision(
                no_additional_action_needed=bool(payload["no_additional_action_needed"]),
                eligible_unrelated_lanes=tuple(payload["eligible_unrelated_lanes"] or ()),
            )
            if not decision.is_valid():
                raise WorkflowStateError(
                    "checkpoint cannot assert no additional action while eligible unrelated lanes exist"
                )
        digest = canonical_payload_sha256(payload)
        checkpoint = WorkflowCheckpoint(
            checkpoint_id=orchestration_identifier(
                "checkpoint", workflow_id, step.step_id, str(workflow.current_attempt), digest
            ),
            workflow_id=workflow_id,
            step_id=step.step_id,
            attempt=workflow.current_attempt,
            payload=payload,
            payload_sha256=digest,
            created_at_utc=current,
        )
        self.store.save_checkpoint(checkpoint)
        updated = workflow.model_copy(
            update={
                "version": workflow.version + 1,
                "last_checkpoint_id": checkpoint.checkpoint_id,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(
            workflow_id,
            "CHECKPOINT_SAVED",
            now=current,
            payload={"checkpoint_id": checkpoint.checkpoint_id, "payload_sha256": digest},
        )
        return checkpoint

    def complete_step(
        self,
        workflow_id: str,
        *,
        result: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> WorkflowInstance:
        current = self._now(now)
        workflow = self.query(workflow_id)
        if workflow.state != WorkflowState.RUNNING:
            raise WorkflowStateError("step completion requires a RUNNING workflow")
        definition = self.store.get_definition(workflow.definition_id)
        if definition is None or workflow.current_step_index >= len(definition.steps):
            raise WorkflowStateError("workflow has no current step")
        step = definition.steps[workflow.current_step_index]
        if step.requires_checkpoint:
            checkpoint = self.store.latest_checkpoint(workflow_id)
            if (
                checkpoint is None
                or checkpoint.step_id != step.step_id
                or checkpoint.attempt != workflow.current_attempt
            ):
                raise WorkflowStateError("step requires a checkpoint from the current attempt")
        is_last = workflow.current_step_index == len(definition.steps) - 1
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.SUCCEEDED if is_last else WorkflowState.RUNNING,
                "version": workflow.version + 1,
                "current_step_index": workflow.current_step_index + 1,
                "current_attempt": 0 if is_last else 1,
                "assigned_worker_id": None,
                "wait_id": None,
                "failure_code": None,
                "failure_message": None,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(
            workflow_id,
            "WORKFLOW_SUCCEEDED" if is_last else "STEP_SUCCEEDED",
            now=current,
            payload={
                "step_id": step.step_id,
                "attempt": workflow.current_attempt,
                "result": result or {},
            },
        )
        return updated

    def fail_step(
        self,
        workflow_id: str,
        *,
        failure_code: str,
        failure_message: str,
        retryable: bool = True,
        now: datetime | None = None,
    ) -> WorkflowInstance:
        current = self._now(now)
        workflow = self.query(workflow_id)
        if workflow.state != WorkflowState.RUNNING:
            raise WorkflowStateError("step failure requires a RUNNING workflow")
        step = self.current_step(workflow_id)
        if step is None:
            raise WorkflowStateError("workflow has no current step")
        can_retry = (
            retryable
            and step.recoverable
            and workflow.current_attempt < step.retry_policy.max_attempts
        )
        if can_retry:
            backoff = step.retry_policy.backoff_seconds(workflow.current_attempt)
            state = WorkflowState.RETRY_SCHEDULED
            retry_at = current + timedelta(seconds=backoff)
        else:
            state = WorkflowState.FAILED
            retry_at = None
        updated = workflow.model_copy(
            update={
                "state": state,
                "version": workflow.version + 1,
                "assigned_worker_id": None,
                "retry_available_at_utc": retry_at,
                "failure_code": failure_code,
                "failure_message": failure_message,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(
            workflow_id,
            "STEP_RETRY_SCHEDULED" if can_retry else "STEP_FAILED",
            now=current,
            payload={
                "step_id": step.step_id,
                "attempt": workflow.current_attempt,
                "failure_code": failure_code,
                "retry_available_at_utc": retry_at.isoformat() if retry_at else None,
            },
        )
        return updated

    def wait_for_signal(
        self,
        workflow_id: str,
        signal_name: str,
        *,
        now: datetime | None = None,
    ) -> DurableWait:
        current = self._now(now)
        workflow = self.query(workflow_id)
        if workflow.state != WorkflowState.RUNNING:
            raise WorkflowStateError("signal wait requires a RUNNING workflow")
        wait = DurableWait(
            wait_id=orchestration_identifier(
                "wait", workflow_id, WaitKind.SIGNAL.value, signal_name, ""
            ),
            workflow_id=workflow_id,
            kind=WaitKind.SIGNAL,
            signal_name=signal_name,
            created_at_utc=current,
        )
        self.store.save_wait(wait)
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.WAITING,
                "version": workflow.version + 1,
                "assigned_worker_id": None,
                "wait_id": wait.wait_id,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(
            workflow_id,
            "WAIT_STARTED",
            now=current,
            payload={"wait_id": wait.wait_id, "signal": signal_name},
        )
        return wait

    def wait_until(
        self,
        workflow_id: str,
        release_at_utc: datetime,
        *,
        now: datetime | None = None,
    ) -> DurableWait:
        current = self._now(now)
        release = release_at_utc.astimezone(UTC)
        if release <= current:
            raise ValueError("release_at_utc must be in the future")
        workflow = self.query(workflow_id)
        if workflow.state != WorkflowState.RUNNING:
            raise WorkflowStateError("timer wait requires a RUNNING workflow")
        wait = DurableWait(
            wait_id=orchestration_identifier(
                "wait", workflow_id, WaitKind.UNTIL.value, "", release.isoformat()
            ),
            workflow_id=workflow_id,
            kind=WaitKind.UNTIL,
            release_at_utc=release,
            created_at_utc=current,
        )
        self.store.save_wait(wait)
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.WAITING,
                "version": workflow.version + 1,
                "assigned_worker_id": None,
                "wait_id": wait.wait_id,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(
            workflow_id,
            "WAIT_STARTED",
            now=current,
            payload={"wait_id": wait.wait_id, "release_at_utc": release.isoformat()},
        )
        return wait

    def signal(
        self,
        signal: WorkflowSignal,
        *,
        now: datetime | None = None,
    ) -> WorkflowInstance:
        current = self._now(now or signal.observed_at_utc)
        workflow = self.query(signal.workflow_id)
        first_delivery = self.store.record_inbox(
            message_id=signal.signal_id,
            workflow_id=signal.workflow_id,
            message_type="SIGNAL",
            payload=signal.model_dump(mode="json"),
            received_at_utc=current,
        )
        if not first_delivery:
            return workflow
        self._event(
            signal.workflow_id,
            "SIGNAL_RECEIVED",
            now=current,
            payload={"signal_id": signal.signal_id, "signal_name": signal.signal_name},
            correlation_id=signal.idempotency_key,
        )
        if workflow.state != WorkflowState.WAITING or not workflow.wait_id:
            return workflow
        wait = self.store.get_wait(workflow.wait_id)
        if wait is None or wait.kind != WaitKind.SIGNAL or wait.signal_name != signal.signal_name:
            return workflow
        satisfied = wait.model_copy(update={"satisfied_at_utc": current, "payload": signal.payload})
        self.store.save_wait(satisfied)
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.RUNNING,
                "version": workflow.version + 1,
                "wait_id": None,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(
            signal.workflow_id, "WAIT_SATISFIED", now=current, payload={"wait_id": wait.wait_id}
        )
        return updated

    def release_due_waits(self, *, now: datetime | None = None) -> tuple[WorkflowInstance, ...]:
        current = self._now(now)
        released: list[WorkflowInstance] = []
        for wait in self.store.due_waits(current):
            workflow = self.query(wait.workflow_id)
            if workflow.state != WorkflowState.WAITING or workflow.wait_id != wait.wait_id:
                continue
            satisfied = wait.model_copy(update={"satisfied_at_utc": current})
            self.store.save_wait(satisfied)
            updated = workflow.model_copy(
                update={
                    "state": WorkflowState.RUNNING,
                    "version": workflow.version + 1,
                    "wait_id": None,
                    "updated_at_utc": current,
                }
            )
            self.store.update_workflow(updated, expected_version=workflow.version)
            self._event(
                workflow.workflow_id,
                "WAIT_SATISFIED",
                now=current,
                payload={"wait_id": wait.wait_id},
            )
            released.append(updated)
        return tuple(released)

    def due_retries(self, *, now: datetime | None = None) -> tuple[WorkflowInstance, ...]:
        current = self._now(now)
        workflows = self.store.workflows_in_states((WorkflowState.RETRY_SCHEDULED,))
        return tuple(
            workflow
            for workflow in workflows
            if workflow.retry_available_at_utc is not None
            and workflow.retry_available_at_utc <= current
        )

    def cancel(self, workflow_id: str, *, now: datetime | None = None) -> WorkflowInstance:
        current = self._now(now)
        workflow = self.query(workflow_id)
        if workflow.state in {
            WorkflowState.SUCCEEDED,
            WorkflowState.FAILED,
            WorkflowState.CANCELLED,
        }:
            return workflow
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.CANCELLED,
                "version": workflow.version + 1,
                "cancel_requested": True,
                "assigned_worker_id": None,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(workflow_id, "WORKFLOW_CANCELLED", now=current)
        return updated

    def suspend(self, workflow_id: str, *, now: datetime | None = None) -> WorkflowInstance:
        current = self._now(now)
        workflow = self.query(workflow_id)
        if workflow.state not in {
            WorkflowState.RUNNING,
            WorkflowState.WAITING,
            WorkflowState.RETRY_SCHEDULED,
        }:
            raise WorkflowStateError(f"cannot suspend workflow from {workflow.state.value}")
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.SUSPENDED,
                "version": workflow.version + 1,
                "assigned_worker_id": None,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(workflow_id, "WORKFLOW_SUSPENDED", now=current)
        return updated

    def resume(self, workflow_id: str, *, now: datetime | None = None) -> WorkflowInstance:
        current = self._now(now)
        workflow = self.query(workflow_id)
        if workflow.state not in {WorkflowState.SUSPENDED, WorkflowState.RECOVERY_REQUIRED}:
            raise WorkflowStateError(f"cannot resume workflow from {workflow.state.value}")
        updated = workflow.model_copy(
            update={
                "state": WorkflowState.RUNNING,
                "version": workflow.version + 1,
                "recovery_count": workflow.recovery_count + 1,
                "assigned_worker_id": None,
                "updated_at_utc": current,
            }
        )
        self.store.update_workflow(updated, expected_version=workflow.version)
        self._event(workflow_id, "WORKFLOW_RESUMED", now=current)
        return updated

    def heartbeat(
        self,
        worker_id: str,
        *,
        fencing_epoch: int,
        ttl_seconds: int = 60,
        capabilities: tuple[str, ...] = (),
        active_workflow_ids: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> WorkerHeartbeat:
        if ttl_seconds < 1 or ttl_seconds > 3600:
            raise ValueError("worker heartbeat ttl_seconds must be between 1 and 3600")
        current = self._now(now)
        heartbeat = WorkerHeartbeat(
            worker_id=worker_id,
            fencing_epoch=fencing_epoch,
            observed_at_utc=current,
            expires_at_utc=current + timedelta(seconds=ttl_seconds),
            capabilities=capabilities,
            active_workflow_ids=active_workflow_ids,
        )
        return self.store.save_worker_heartbeat(heartbeat)
