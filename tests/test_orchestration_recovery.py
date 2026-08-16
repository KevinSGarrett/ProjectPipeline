from datetime import UTC, datetime, timedelta

from project_pipeline.domain.orchestration import (
    DurableBackendKind,
    DurableOperation,
    DurableOperationState,
    WorkflowDefinition,
    WorkflowStartRequest,
    WorkflowState,
    WorkflowStepDefinition,
    canonical_payload_sha256,
    orchestration_identifier,
)
from project_pipeline.orchestration.persistence import OrchestrationStore
from project_pipeline.orchestration.recovery import RecoveryManager
from project_pipeline.orchestration.runtime import LocalDurableRuntime

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def setup(tmp_path, project_root, *, recoverable=True):
    store = OrchestrationStore(tmp_path / "state.sqlite", project_root)
    store.initialize()
    runtime = LocalDurableRuntime(store)
    definition = WorkflowDefinition(
        definition_id=orchestration_identifier("workflow_definition", "recover", "1"),
        workflow_name="recover",
        version="1",
        steps=(WorkflowStepDefinition(step_id="work", name="Work", recoverable=recoverable),),
    )
    runtime.register_definition(definition)
    workflow = runtime.start(
        WorkflowStartRequest(definition_id=definition.definition_id, idempotency_key="r1"), now=NOW
    )
    return store, runtime, workflow


def test_stale_worker_schedules_safe_retry(tmp_path, project_root):
    store, runtime, workflow = setup(tmp_path, project_root)
    runtime.heartbeat("worker", fencing_epoch=1, ttl_seconds=5, now=NOW)
    runtime.assign_worker(workflow.workflow_id, "worker", fencing_epoch=1, now=NOW)
    decisions = RecoveryManager(store, runtime).recover_stale_workers(
        now=NOW + timedelta(seconds=6)
    )
    assert decisions[0].safe_to_automate is True
    assert runtime.query(workflow.workflow_id).state == WorkflowState.RETRY_SCHEDULED
    store.close()


def test_stale_worker_marks_nonrecoverable_work_manual(tmp_path, project_root):
    store, runtime, workflow = setup(tmp_path, project_root, recoverable=False)
    runtime.heartbeat("worker", fencing_epoch=1, ttl_seconds=5, now=NOW)
    runtime.assign_worker(workflow.workflow_id, "worker", fencing_epoch=1, now=NOW)
    decisions = RecoveryManager(store, runtime).recover_stale_workers(
        now=NOW + timedelta(seconds=6)
    )
    assert decisions[0].safe_to_automate is False
    assert runtime.query(workflow.workflow_id).state == WorkflowState.RECOVERY_REQUIRED
    store.close()


def test_unknown_outcome_requires_reconciliation_not_retry(tmp_path, project_root):
    store, runtime, workflow = setup(tmp_path, project_root)
    payload = {"x": 1}
    digest = canonical_payload_sha256(payload)
    operation = DurableOperation(
        operation_id=orchestration_identifier(
            "operation", workflow.workflow_id, "START_WORKFLOW", "op1"
        ),
        workflow_id=workflow.workflow_id,
        operation_type="START_WORKFLOW",
        idempotency_key="op1",
        state=DurableOperationState.UNKNOWN_OUTCOME,
        payload=payload,
        payload_sha256=digest,
        backend=DurableBackendKind.HATCHET,
        attempt_count=1,
        created_at_utc=NOW,
        updated_at_utc=NOW,
    )
    store.save_operation(operation)
    manager = RecoveryManager(store, runtime)
    decisions = manager.unknown_outcome_decisions(now=NOW)
    assert decisions[0].safe_to_automate is False
    assert store.get_operation(operation.operation_id).attempt_count == 1
    store.close()


def test_reconciliation_only_requeues_after_effect_is_proven_absent(tmp_path, project_root):
    store, runtime, workflow = setup(tmp_path, project_root)
    payload = {"x": 1}
    digest = canonical_payload_sha256(payload)
    operation = DurableOperation(
        operation_id=orchestration_identifier(
            "operation", workflow.workflow_id, "START_WORKFLOW", "op1"
        ),
        workflow_id=workflow.workflow_id,
        operation_type="START_WORKFLOW",
        idempotency_key="op1",
        state=DurableOperationState.UNKNOWN_OUTCOME,
        payload=payload,
        payload_sha256=digest,
        backend=DurableBackendKind.HATCHET,
        attempt_count=1,
        created_at_utc=NOW,
        updated_at_utc=NOW,
    )
    store.save_operation(operation)
    manager = RecoveryManager(store, runtime)
    unchanged = manager.reconcile_operation(operation.operation_id, lambda _: "UNKNOWN", now=NOW)
    assert unchanged.state == DurableOperationState.UNKNOWN_OUTCOME
    pending = manager.reconcile_operation(
        operation.operation_id, lambda _: "NOT_APPLIED", now=NOW + timedelta(seconds=1)
    )
    assert pending.state == DurableOperationState.PENDING and pending.attempt_count == 1
    store.close()
