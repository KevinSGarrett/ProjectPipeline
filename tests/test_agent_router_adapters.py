import json
import subprocess
import sys

import pytest

from project_pipeline.agent_router import (
    AnthropicMessagesAdapter,
    GeminiGenerateContentAdapter,
    LocalProcessProviderAdapter,
    MockToolAdapter,
    OpenAIResponsesAdapter,
    ProviderAdapterError,
)
from project_pipeline.domain import ExecutionTaskContract


def contract():
    return ExecutionTaskContract(
        task_id="T",
        task_class="reasoning",
        required_capabilities=("routine_reasoning",),
        instructions="hello",
    )


def test_openai_responses_adapter_normalizes_payload_and_usage():
    seen = {}

    def transport(method, url, headers, body, timeout):
        seen.update(method=method, url=url, headers=headers, body=json.loads(body))
        return (
            200,
            {},
            json.dumps(
                {
                    "id": "r1",
                    "status": "completed",
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": "ok"}]}
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                }
            ).encode(),
        )

    result = OpenAIResponsesAdapter("secret", transport=transport).execute(
        contract(), model_name="qualified-model"
    )
    assert seen["url"].endswith("/v1/responses") and seen["body"]["store"] is False
    assert result.output["text"] == "ok" and result.usage.input_units == 5


def test_anthropic_messages_adapter_normalizes_payload_and_usage():
    seen = {}

    def transport(method, url, headers, body, timeout):
        seen.update(headers=headers, body=json.loads(body))
        return (
            200,
            {},
            json.dumps(
                {
                    "id": "m1",
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 3, "output_tokens": 4},
                    "stop_reason": "end_turn",
                }
            ).encode(),
        )

    result = AnthropicMessagesAdapter("secret", transport=transport).execute(
        contract(), model_name="qualified-model"
    )
    assert seen["headers"]["anthropic-version"] == "2023-06-01" and result.usage.output_units == 4


def test_gemini_generate_content_adapter_normalizes_payload_and_usage():
    seen = {}

    def transport(method, url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=json.loads(body))
        return (
            200,
            {},
            json.dumps(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}
                    ],
                    "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1},
                }
            ).encode(),
        )

    result = GeminiGenerateContentAdapter("secret", transport=transport).execute(
        contract(), model_name="qualified-model"
    )
    assert (
        ":generateContent" in seen["url"]
        and "x-goog-api-key" in seen["headers"]
        and result.output["text"] == "ok"
    )


def test_http_rate_limit_is_typed_retryable_error():
    def transport(*args):
        return 429, {}, b'{"error":"limit"}'

    with pytest.raises(ProviderAdapterError) as e:
        OpenAIResponsesAdapter("x", transport=transport).execute(contract(), model_name="m")
    assert e.value.retryable and e.value.kind == "RATE_LIMIT"


def test_local_process_adapter_uses_no_shell_and_parses_json():
    code = 'import sys,json; x=json.load(sys.stdin); print(json.dumps({"output":{"echo":x["task"]["task_id"]},"usage":{"input_units":1}}))'
    result = LocalProcessProviderAdapter((sys.executable, "-c", code)).execute(
        contract(), model_name="local"
    )
    assert result.output["echo"] == "T" and result.usage.input_units == 1


def test_hosted_connection_loss_is_unknown_outcome():
    def transport(*args):
        raise OSError("connection reset")

    with pytest.raises(ProviderAdapterError) as error:
        OpenAIResponsesAdapter("x", transport=transport).execute(contract(), model_name="m")
    assert error.value.kind == "UNKNOWN_OUTCOME"
    assert error.value.retryable is True


def test_local_process_loss_is_not_retryable(monkeypatch):
    class Lost:
        returncode = -9
        stdout = b""
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Lost())
    with pytest.raises(ProviderAdapterError) as error:
        LocalProcessProviderAdapter((sys.executable, "-c", "pass")).execute(
            contract(), model_name="local"
        )
    assert error.value.kind == "PROCESS_LOSS"
    assert error.value.retryable is False


def test_mock_tool_adapter_enforces_operation_allowlist():
    tool = MockToolAdapter({"tool:test": {"read"}})
    assert tool.invoke("tool:test", "read", {"x": 1})["outcome"] == "MOCK_VERIFIED"
    with pytest.raises(ProviderAdapterError):
        tool.invoke("tool:test", "write", {})
