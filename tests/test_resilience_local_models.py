from project_pipeline.domain.resilience import RuntimeKind
from project_pipeline.resilience.local_models import LocalModelGateway, load_local_runtimes


def test_local_runtime_config_is_private_and_advisory(project_root):
    g = LocalModelGateway(load_local_runtimes(project_root))
    assert g.validate() == []
    assert all(r.advisory_only for r in g.runtimes)


def test_local_runtime_fallback_selection(project_root):
    g = LocalModelGateway(load_local_runtimes(project_root))
    r = g.select(("summarization",), available_kinds=(RuntimeKind.LLAMA_CPP,))
    assert r and r.kind is RuntimeKind.LLAMA_CPP


def test_local_request_plan_never_claims_control_authority(project_root):
    g = LocalModelGateway(load_local_runtimes(project_root))
    r = g.select(("triage",))
    plan = g.plan_request(r, model="local-model", task_kind="triage")
    assert not plan["deterministic_control_authority"] and not plan["live_invocation_performed"]
