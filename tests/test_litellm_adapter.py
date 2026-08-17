from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.agent_router.adapters import LiteLLMProxyAdapter, build_adapter
from project_pipeline.agent_router.registry import load_agent_registry
from project_pipeline.domain import ExecutionTaskContract


def test_litellm_proxy_adapter_uses_openai_compatible_gateway_boundary() -> None:
    seen = {}

    def transport(method, url, headers, body, timeout):
        seen.update(method=method, url=url, headers=dict(headers), body=json.loads(body))
        payload = {
            "id": "chat-1",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 3,
                "prompt_tokens_details": {"cached_tokens": 2},
            },
        }
        return 200, {}, json.dumps(payload).encode()

    contract = ExecutionTaskContract(
        task_id="T",
        task_class="reasoning",
        required_capabilities=("routine_reasoning",),
        instructions="hello",
    )
    result = LiteLLMProxyAdapter("secret", transport=transport).execute(
        contract, model_name="provider/model"
    )
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["body"]["messages"][0]["content"] == "hello"
    assert result.output["text"] == "ok" and result.usage.cached_input_units == 2
    assert result.evidence_references == ("UPSTREAM-012",)


def test_litellm_registry_entry_is_transport_only_and_factory_built() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_agent_registry(root)
    provider = next(item for item in registry.providers if item.provider_id == "provider:litellm-proxy")
    assert provider.enabled is False
    assert "routing authority" in " ".join(provider.constraints)
    adapter = build_adapter(provider.adapter_id, api_key="")
    assert adapter.adapter_id == "adapter:litellm-proxy"
    secret = LiteLLMProxyAdapter("super-secret-key")
    assert "super-secret-key" not in json.dumps(secret.health())
