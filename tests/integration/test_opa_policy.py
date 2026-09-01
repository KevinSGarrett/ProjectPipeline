from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from project_pipeline.ports import ActionContext
from project_pipeline.upstream_integrations.security import ConftestAdapter, OpaAdapter

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def context() -> ActionContext:
    return ActionContext(
        actor_id="actor:test",
        correlation_id="corr:pp168",
        idempotency_key="idem:pp168-1",
        authority_scope=("policy",),
    )


def test_opa_module_path_exists() -> None:
    assert (ROOT / "integrations/policy/opa.py").is_file()


def test_canonical_deny_without_authorization(context: ActionContext) -> None:
    from integrations.policy.opa import OpaConformancePolicyPort

    port = OpaConformancePolicyPort(repository_root=ROOT, opa=OpaAdapter(executable="missing-opa"))
    decision = port.evaluate(
        "merge",
        {"authorized": False, "high_impact": True, "independent_approval": False},
        context,
    )
    assert decision.allowed is False
    assert "not authorized" in decision.reasons[0]


def test_high_impact_requires_independent_approval(context: ActionContext) -> None:
    from integrations.policy.opa import OpaConformancePolicyPort

    port = OpaConformancePolicyPort(repository_root=ROOT, opa=OpaAdapter(executable="missing-opa"))
    decision = port.evaluate(
        "merge",
        {"authorized": True, "high_impact": True, "independent_approval": False},
        context,
    )
    assert decision.allowed is False
    assert decision.required_approvals == ("independent_approval",)


def test_allow_when_authorized_and_approved(context: ActionContext) -> None:
    from integrations.policy.opa import OpaConformancePolicyPort

    port = OpaConformancePolicyPort(repository_root=ROOT, opa=OpaAdapter(executable="missing-opa"))
    decision = port.evaluate(
        "read",
        {"authorized": True, "high_impact": False, "independent_approval": False},
        context,
    )
    assert decision.allowed is True
    assert port.last_observation is not None
    assert port.last_observation.available is False


def test_conftest_plan_confines_target(context: ActionContext) -> None:
    from integrations.policy.opa import OpaConformancePolicyPort

    port = OpaConformancePolicyPort(
        repository_root=ROOT,
        conftest=ConftestAdapter(executable="conftest"),
    )
    plan = port.plan_conftest(Path("config/security_policy.json"))
    assert Path(plan.argv[-1]) == (ROOT / "config/security_policy.json").resolve()
    with pytest.raises(ValueError):
        port.plan_conftest(Path("../outside"))


def test_opa_conformance_deny_can_only_tighten(context: ActionContext) -> None:
    from integrations.policy.opa import OpaConformancePolicyPort

    class FakeOpa(OpaAdapter):
        def available(self) -> bool:
            return True

        def plan_eval(self, root, *, policy_dir, query, input_document):
            return SimpleNamespace(
                argv=("opa", "eval"),
                cwd=str(root),
                evidence_sources=("open-policy-agent/opa:docs",),
            )

        def execute(self, plan):
            return SimpleNamespace(returncode=0, stdout='{"allow": false, "deny": ["rego deny"]}')

    fake = FakeOpa()
    fake._execute_enabled = True
    port = OpaConformancePolicyPort(repository_root=ROOT, opa=fake)
    decision = port.evaluate(
        "read",
        {"authorized": True, "high_impact": False, "independent_approval": False},
        context,
    )
    assert decision.allowed is False
    assert any("rego deny" in reason or "CONFORM" in decision.decision_id for reason in decision.reasons)


def test_policy_dir_escape_rejected() -> None:
    from integrations.policy.opa import OpaConformancePolicyPort

    with pytest.raises((ValueError, FileNotFoundError)):
        OpaConformancePolicyPort(
            repository_root=ROOT,
            policy_dir=Path("../outside"),
            opa=OpaAdapter(executable="missing-opa"),
        )
