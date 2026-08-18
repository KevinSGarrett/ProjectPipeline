from datetime import UTC, datetime, timedelta

import pytest

from project_pipeline.domain.orchestration import (
    DurableBackendKind,
    RetryPolicy,
    WorkflowDefinition,
    WorkflowSignal,
    WorkflowStartRequest,
    WorkflowState,
    WorkflowStepDefinition,
    orchestration_identifier,
)
from project_pipeline.orchestration.persistence import (
    OrchestrationConflictError,
    OrchestrationStore,
)
from project_pipeline.orchestration.runtime import LocalDurableRuntime, WorkflowStateError

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def make_definition(*, checkpoint=False, attempts=3):
    return WorkflowDefinition(
        definition_id=orchestration_identifier("workflow_definition", "build-project", "1"),
        workflow_name="build-project",
        version="1",
        steps=(
            WorkflowStepDefinition(
                step_id="compile",
                name="Compile",
                retry_policy=RetryPolicy(
                    max_attempts=attempts,
                    initial_backoff_seconds=5,
                    multiplier=2,
                    max_backoff_seconds=30,
                ),
                requires_checkpoint=checkpoint,
            ),
            WorkflowStepDefinition(step_id="verify", name="Verify"),
        ),
    )


def setup_runtime(tmp_path, root, *, checkpoint=False, attempts=3):
    store = OrchestrationStore(tmp_path / "state.sqlite", root)
    store.initialize()
    runtime = LocalDurableRuntime(store)
    definition = make_definition(checkpoint=checkpoint, attempts=attempts)
    runtime.register_definition(definition)
    request = WorkflowStartRequest(
        definition_id=definition.definition_id,
        idempotency_key="idem-1",
        input_payload={"project": "demo"},
        backend=DurableBackendKind.LOCAL_REFERENCE,
    )
    workflow = runtime.start(request, now=NOW)
    return store, runtime, definition, workflow


def test_start_is_idempotent(tmp_path, project_root):
    store, runtime, definition, first = setup_runtime(tmp_path, project_root)
    request = WorkflowStartRequest(
        definition_id=definition.definition_id,
        idempotency_key="idem-1",
        input_payload={"project": "demo"},
    )
    second = runtime.start(request, now=NOW + timedelta(seconds=1))
    assert first == second
    assert len(store.events(first.workflow_id)) == 1
    store.close()


def test_start_rejects_idempotency_reuse_with_different_input(tmp_path, project_root):
    store, runtime, definition, _ = setup_runtime(tmp_path, project_root)
    with pytest.raises(WorkflowStateError):
        runtime.start(
            WorkflowStartRequest(
                definition_id=definition.definition_id,
                idempotency_key="idem-1",
                input_payload={"project": "different"},
            ),
            now=NOW,
        )
    store.close()


def test_worker_assignment_requires_current_fencing_epoch(tmp_path, project_root):
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root)
    runtime.heartbeat("worker-1", fencing_epoch=3, now=NOW)
    with pytest.raises(WorkflowStateError):
        runtime.assign_worker(workflow.workflow_id, "worker-1", fencing_epoch=2, now=NOW)
    assigned = runtime.assign_worker(workflow.workflow_id, "worker-1", fencing_epoch=3, now=NOW)
    assert assigned.assigned_worker_id == "worker-1"
    store.close()


def test_stale_heartbeat_epoch_is_rejected(tmp_path, project_root):
    store, runtime, _, _ = setup_runtime(tmp_path, project_root)
    runtime.heartbeat("worker-1", fencing_epoch=3, now=NOW)
    with pytest.raises(OrchestrationConflictError):
        runtime.heartbeat("worker-1", fencing_epoch=2, now=NOW + timedelta(seconds=1))
    store.close()


def test_retry_is_scheduled_with_deterministic_backoff(tmp_path, project_root):
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root)
    failed = runtime.fail_step(
        workflow.workflow_id, failure_code="TEMP", failure_message="temporary", now=NOW
    )
    assert failed.state == WorkflowState.RETRY_SCHEDULED
    assert failed.retry_available_at_utc == NOW + timedelta(seconds=5)
    assert runtime.due_retries(now=NOW + timedelta(seconds=4)) == ()
    assert (
        runtime.due_retries(now=NOW + timedelta(seconds=5))[0].workflow_id == workflow.workflow_id
    )
    store.close()


def test_retry_exhaustion_fails_workflow(tmp_path, project_root):
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root, attempts=1)
    failed = runtime.fail_step(
        workflow.workflow_id, failure_code="PERM", failure_message="permanent", now=NOW
    )
    assert failed.state == WorkflowState.FAILED
    store.close()


def test_checkpoint_required_before_completion(tmp_path, project_root):
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root, checkpoint=True)
    with pytest.raises(WorkflowStateError):
        runtime.complete_step(workflow.workflow_id, now=NOW)
    checkpoint = runtime.checkpoint(workflow.workflow_id, {"cursor": 10}, now=NOW)
    advanced = runtime.complete_step(workflow.workflow_id, now=NOW + timedelta(seconds=1))
    assert advanced.current_step_index == 1
    assert advanced.last_checkpoint_id == checkpoint.checkpoint_id
    store.close()


def test_checkpoint_rejects_invalid_no_additional_action_decision(tmp_path, project_root):
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root, checkpoint=True)
    with pytest.raises(WorkflowStateError):
        runtime.checkpoint(
            workflow.workflow_id,
            {
                "no_additional_action_needed": True,
                "eligible_unrelated_lanes": ["lane:local-governed"],
            },
            now=NOW,
        )
    store.close()


def test_signal_wait_is_durable_and_duplicate_signal_is_idempotent(tmp_path, project_root):
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root)
    wait = runtime.wait_for_signal(workflow.workflow_id, "human.fixed", now=NOW)
    signal = WorkflowSignal(
        signal_id=orchestration_identifier("signal", workflow.workflow_id, "human.fixed", "sig-1"),
        workflow_id=workflow.workflow_id,
        signal_name="human.fixed",
        idempotency_key="sig-1",
        payload={"ok": True},
        observed_at_utc=NOW + timedelta(seconds=2),
    )
    resumed = runtime.signal(signal)
    assert resumed.state == WorkflowState.RUNNING
    assert store.get_wait(wait.wait_id).satisfied_at_utc is not None
    event_count = len(store.events(workflow.workflow_id))
    duplicate = runtime.signal(signal)
    assert duplicate.state == WorkflowState.RUNNING
    assert len(store.events(workflow.workflow_id)) == event_count
    store.close()


def test_timer_wait_survives_store_reopen(tmp_path, project_root):
    db = tmp_path / "state.sqlite"
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root)
    runtime.wait_until(workflow.workflow_id, NOW + timedelta(minutes=5), now=NOW)
    store.close()
    store2 = OrchestrationStore(db, project_root)
    store2.initialize()
    runtime2 = LocalDurableRuntime(store2)
    assert runtime2.release_due_waits(now=NOW + timedelta(minutes=4)) == ()
    released = runtime2.release_due_waits(now=NOW + timedelta(minutes=5))
    assert released[0].state == WorkflowState.RUNNING
    store2.close()


def test_multi_step_success_reaches_terminal_state(tmp_path, project_root):
    store, runtime, _, workflow = setup_runtime(tmp_path, project_root)
    first = runtime.complete_step(workflow.workflow_id, result={"ok": 1}, now=NOW)
    assert first.state == WorkflowState.RUNNING and first.current_step_index == 1
    final = runtime.complete_step(
        workflow.workflow_id, result={"ok": 2}, now=NOW + timedelta(seconds=1)
    )
    assert final.state == WorkflowState.SUCCEEDED
    assert final.current_step_index == 2
    store.close()
