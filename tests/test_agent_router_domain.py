from datetime import UTC, datetime

import pytest

from project_pipeline.agent_router import (
    REQUIRED_ADAPTER_CHECKS,
    MockProviderAdapter,
    accept_qualification_report,
    build_registry,
    qualification_report,
    run_adapter_qualification,
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


def test_registry_rejects_duplicate_ids_and_incompatible_capabilities():
    cap, provider, model, agent = _base()
    duplicate = provider.model_copy()
    with pytest.raises(ValueError, match="duplicate provider"):
        build_registry(
            capabilities=(cap,),
            providers=(provider, duplicate),
            models=(model,),
            agents=(agent,),
        )
    extra = CapabilitySpec(capability_id="visual_review", description="vision")
    incompatible = agent.model_copy(update={"capabilities": (extra.capability_id,)})
    with pytest.raises(ValueError, match="incompatible"):
        build_registry(
            capabilities=(cap, extra),
            providers=(provider,),
            models=(model,),
            agents=(incompatible,),
        )


def test_registry_rejects_secret_values_and_exposes_execution_targets():
    from project_pipeline.agent_router.registry import execution_targets

    cap, provider, model, agent = _base()
    leaked = provider.model_copy(update={"constraints": ("sk-abcdefghijklmnopqrstuvwxyz",)})
    with pytest.raises(ValueError, match="secret"):
        build_registry(capabilities=(cap,), providers=(leaked,), models=(model,), agents=(agent,))
    registry = build_registry(
        capabilities=(cap,), providers=(provider,), models=(model,), agents=(agent,)
    )
    targets = execution_targets(registry)
    assert targets[0]["target_id"] == model.model_id
    assert targets[0]["adapter_id"] == provider.adapter_id
    encoded = registry.model_dump_json()
    restored = type(registry).model_validate_json(encoded)
    assert restored.registry_id == registry.registry_id


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


def test_run_adapter_qualification_invokes_adapter_and_rejects_stale_or_forged_reports():
    adapter = MockProviderAdapter("provider:test")
    report = run_adapter_qualification(adapter, rollback_ready=True)
    assert report.state is QualificationState.QUALIFIED
    accepted = accept_qualification_report(
        report,
        expected_subject_id=adapter.adapter_id,
        expected_subject_version=adapter.adapter_version,
    )
    assert accepted.report_id == report.report_id
    stale = report.model_copy(update={"evaluated_at_utc": datetime(2020, 1, 1, tzinfo=UTC)})
    with pytest.raises(ValueError, match="stale"):
        accept_qualification_report(
            stale,
            expected_subject_id=adapter.adapter_id,
            expected_subject_version=adapter.adapter_version,
        )
    forged = report.model_copy(update={"report_id": "QUAL-forged"})
    with pytest.raises(ValueError, match="forged"):
        accept_qualification_report(
            forged,
            expected_subject_id=adapter.adapter_id,
            expected_subject_version=adapter.adapter_version,
        )
