from __future__ import annotations

import json

from project_pipeline.agent_router.adapters import LiteLLMProxyAdapter
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
