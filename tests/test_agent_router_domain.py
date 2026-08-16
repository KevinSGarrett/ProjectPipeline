from datetime import UTC, datetime

import pytest

from project_pipeline.agent_router import (
    REQUIRED_ADAPTER_CHECKS,
    build_registry,
    qualification_report,
)
from project_pipeline.domain import (
    AgentSpec,
    CapabilitySpec,
    ExecutionMode,
    ExecutionTaskContract,
    ModelSpec,
    ProviderSpec,
    QualificationCheckResult,
    QualificationState,
)


def _base():
    cap = CapabilitySpec(capability_id="routine_reasoning", description="reason")
    provider = ProviderSpec(
        provider_id="provider:test",
        display_name="Test",
        adapter_id="adapter:test",
        execution_mode=ExecutionMode.MOCK,
        capabilities=(cap.capability_id,),
    )
    model = ModelSpec(
        model_id="model:test",
        provider_id=provider.provider_id,
        provider_model_name="test",
        version="1",
        capabilities=(cap.capability_id,),
        qualification=QualificationState.QUALIFIED,
    )
    agent = AgentSpec(
        agent_id="agent:test",
        model_id=model.model_id,
        capabilities=(cap.capability_id,),
        qualification=QualificationState.QUALIFIED,
    )
    return cap, provider, model, agent


def test_registry_identity_is_deterministic():
    cap, p, m, a = _base()
    when = datetime(2026, 1, 1, tzinfo=UTC)
    x = build_registry(capabilities=(cap,), providers=(p,), models=(m,), agents=(a,), when=when)
    y = build_registry(capabilities=(cap,), providers=(p,), models=(m,), agents=(a,), when=when)
    assert x.registry_id == y.registry_id


def test_registry_rejects_unknown_provider_link():
    cap, p, m, a = _base()
    bad = m.model_copy(update={"provider_id": "provider:missing"})
    with pytest.raises(ValueError):
        build_registry(capabilities=(cap,), providers=(p,), models=(bad,), agents=(a,))


def test_task_contract_requires_capability_identifiers():
    with pytest.raises(ValueError):
        ExecutionTaskContract(
            task_id="T", task_class="x", required_capabilities=("Bad Capability",), instructions="x"
        )


def test_adapter_qualification_requires_every_standard_check_and_rollback():
    checks = [QualificationCheckResult(check_name=n, passed=True) for n in REQUIRED_ADAPTER_CHECKS]
    assert (
        qualification_report("adapter:test", "1", checks, rollback_ready=True).state
        is QualificationState.QUALIFIED
    )
    assert (
        qualification_report("adapter:test", "1", checks[:-1], rollback_ready=True).state
        is QualificationState.QUARANTINED
    )
    assert (
        qualification_report("adapter:test", "1", checks, rollback_ready=False).state
        is QualificationState.QUARANTINED
    )
