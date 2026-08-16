from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from project_pipeline.domain.orchestration import (
    DurableBackendKind,
    DurableOperation,
    DurableOperationState,
    DurableWait,
    RetryPolicy,
    WaitKind,
    WorkflowCheckpoint,
    WorkflowDefinition,
    WorkflowStepDefinition,
    canonical_payload_sha256,
    orchestration_identifier,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def definition():
    return WorkflowDefinition(
        definition_id=orchestration_identifier("workflow_definition", "build-project", "1"),
        workflow_name="build-project",
        version="1",
        steps=(WorkflowStepDefinition(step_id="compile", name="Compile"),),
    )


def test_orchestration_identifier_is_deterministic():
    assert orchestration_identifier("workflow", "a", "b") == orchestration_identifier(
        "workflow", "a", "b"
    )
    assert orchestration_identifier("workflow", "a", "b") != orchestration_identifier(
        "workflow", "a", "c"
    )


def test_definition_identity_is_verified():
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            definition_id="WFDEF-000000000000000000000000",
            workflow_name="build-project",
            version="1",
            steps=(WorkflowStepDefinition(step_id="compile", name="Compile"),),
        )


def test_definition_rejects_duplicate_steps():
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            definition_id=orchestration_identifier("workflow_definition", "build-project", "1"),
            workflow_name="build-project",
            version="1",
            steps=(
                WorkflowStepDefinition(step_id="compile", name="Compile"),
                WorkflowStepDefinition(step_id="compile", name="Compile again"),
            ),
        )


def test_retry_policy_is_bounded_and_deterministic():
    policy = RetryPolicy(
        max_attempts=5, initial_backoff_seconds=2, multiplier=3, max_backoff_seconds=10
    )
    assert [policy.backoff_seconds(i) for i in (1, 2, 3, 4)] == [2, 6, 10, 10]


def test_signal_wait_requires_signal_name():
    with pytest.raises(ValidationError):
        DurableWait(
            wait_id=orchestration_identifier("wait", "WFRUN-X", WaitKind.SIGNAL.value, "", ""),
            workflow_id="WFRUN-X",
            kind=WaitKind.SIGNAL,
            created_at_utc=NOW,
        )


def test_checkpoint_hash_and_identity_are_verified():
    payload = {"position": 42}
    digest = canonical_payload_sha256(payload)
    item = WorkflowCheckpoint(
        checkpoint_id=orchestration_identifier("checkpoint", "WFRUN-X", "compile", "1", digest),
        workflow_id="WFRUN-X",
        step_id="compile",
        attempt=1,
        payload=payload,
        payload_sha256=digest,
        created_at_utc=NOW,
    )
    assert item.payload_sha256 == digest
    with pytest.raises(ValidationError):
        item.model_copy(update={"payload_sha256": "0" * 64}).model_validate(
            item.model_copy(update={"payload_sha256": "0" * 64}).model_dump()
        )


def test_operation_identity_and_payload_hash_are_verified():
    payload = {"x": 1}
    digest = canonical_payload_sha256(payload)
    operation = DurableOperation(
        operation_id=orchestration_identifier("operation", "WFRUN-X", "START_WORKFLOW", "idem"),
        workflow_id="WFRUN-X",
        operation_type="START_WORKFLOW",
        idempotency_key="idem",
        state=DurableOperationState.PENDING,
        payload=payload,
        payload_sha256=digest,
        backend=DurableBackendKind.HATCHET,
        created_at_utc=NOW,
        updated_at_utc=NOW,
    )
    assert operation.state == DurableOperationState.PENDING
