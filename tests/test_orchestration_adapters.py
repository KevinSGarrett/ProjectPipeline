from datetime import UTC, datetime

import pytest

from project_pipeline.domain.orchestration import (
    BackendQualificationState,
    DurableBackendKind,
    WorkflowDefinition,
    WorkflowStartRequest,
    WorkflowState,
    WorkflowStepDefinition,
    orchestration_identifier,
)
from project_pipeline.orchestration.adapters import (
    BackendUnavailableError,
    DBOSFallbackAdapter,
    HatchetDurableAdapter,
    HatchetSdkBridge,
    MockDurableBackend,
    TemporalFallbackAdapter,
)
from project_pipeline.orchestration.persistence import OrchestrationStore
from project_pipeline.orchestration.runtime import LocalDurableRuntime
from project_pipeline.orchestration.service import FailoverPlanner, OrchestrationService

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


class FakeRef:
    workflow_run_id = "hatchet-run-1"


class FakeWorkflow:
    def __init__(self):
        self.calls = []

    def run(self, payload, **kwargs):
        self.calls.append((payload, kwargs))
        return FakeRef()


def request(backend=DurableBackendKind.HATCHET):
    definition_id = orchestration_identifier("workflow_definition", "external", "1")
    return WorkflowStartRequest(
        definition_id=definition_id, idempotency_key="x1", input_payload={"x": 1}, backend=backend
    )


def test_hatchet_bridge_uses_nonblocking_run_and_metadata():
    workflow = FakeWorkflow()
    bridge = HatchetSdkBridge(lambda name: workflow)
    receipt = bridge.start("external", request())
    assert receipt.backend_run_id == "hatchet-run-1"
    assert workflow.calls[0][1]["wait_for_result"] is False
    assert workflow.calls[0][1]["additional_metadata"]["project_pipeline_idempotency_key"] == "x1"


def test_hatchet_adapter_reports_configuration_truthfully():
    adapter = HatchetDurableAdapter()
    assert adapter.capabilities().qualification in {
        BackendQualificationState.DEPENDENCY_UNAVAILABLE,
        BackendQualificationState.CONFIGURATION_REQUIRED,
    }
    with pytest.raises(BackendUnavailableError):
        adapter.start(request(), workflow_name="external")


def test_fallback_adapters_fail_closed_without_live_qualification():
    for adapter in (DBOSFallbackAdapter(), TemporalFallbackAdapter()):
        assert adapter.capabilities().qualification != BackendQualificationState.LIVE_VERIFIED
        with pytest.raises(BackendUnavailableError):
            adapter.start(request(adapter.backend), workflow_name="external")


def setup_service(tmp_path, project_root, backend):
    store = OrchestrationStore(tmp_path / "state.sqlite", project_root)
    store.initialize()
    runtime = LocalDurableRuntime(store)
    definition = WorkflowDefinition(
        definition_id=orchestration_identifier("workflow_definition", "external", "1"),
        workflow_name="external",
        version="1",
        steps=(WorkflowStepDefinition(step_id="one", name="One"),),
    )
    runtime.register_definition(definition)
    service = OrchestrationService(store, runtime, {DurableBackendKind.MOCK: backend})
    return store, runtime, service, definition


def test_service_persists_remote_ack_and_backend_identity(tmp_path, project_root):
    backend = MockDurableBackend()
    store, _runtime, service, definition = setup_service(tmp_path, project_root, backend)
    workflow = service.start(
        WorkflowStartRequest(
            definition_id=definition.definition_id,
            idempotency_key="m1",
            backend=DurableBackendKind.MOCK,
        ),
        workflow_name="external",
        now=NOW,
    )
    assert workflow.backend_run_id
    assert (
        store.operations_by_state.__self__.get_operation(
            orchestration_identifier("operation", workflow.workflow_id, "START_WORKFLOW", "m1")
        ).state.value
        == "ACKNOWLEDGED"
    )
    store.close()


def test_lost_remote_ack_becomes_unknown_outcome_without_blind_retry(tmp_path, project_root):
    backend = MockDurableBackend()
    backend.lose_next_start_response = True
    store, _runtime, service, definition = setup_service(tmp_path, project_root, backend)
    workflow = service.start(
        WorkflowStartRequest(
            definition_id=definition.definition_id,
            idempotency_key="m1",
            backend=DurableBackendKind.MOCK,
        ),
        workflow_name="external",
        now=NOW,
    )
    assert workflow.state == WorkflowState.RECOVERY_REQUIRED
    assert backend.start_calls == 1
    service.start(
        WorkflowStartRequest(
            definition_id=definition.definition_id,
            idempotency_key="m1",
            backend=DurableBackendKind.MOCK,
        ),
        workflow_name="external",
        now=NOW,
    )
    assert backend.start_calls == 1
    store.close()


def test_failover_planner_blocks_active_external_history(tmp_path, project_root):
    backend = MockDurableBackend()
    store, _runtime, service, definition = setup_service(tmp_path, project_root, backend)
    workflow = service.start(
        WorkflowStartRequest(
            definition_id=definition.definition_id,
            idempotency_key="m1",
            backend=DurableBackendKind.MOCK,
        ),
        workflow_name="external",
        now=NOW,
    )
    allowed, reason = FailoverPlanner.can_failover(workflow, DurableBackendKind.HATCHET)
    assert allowed is False and "cannot be silently migrated" in reason
    store.close()
