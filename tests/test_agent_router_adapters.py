import json
import subprocess
import sys
from pathlib import Path

import pytest

from project_pipeline.agent_router import (
    AnthropicMessagesAdapter,
    CursorCliProviderAdapter,
    GeminiGenerateContentAdapter,
    LocalProcessProviderAdapter,
    MockProviderAdapter,
    MockToolAdapter,
    OpenAIResponsesAdapter,
    ProviderAdapterError,
    build_adapter,
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


def test_build_adapter_is_provider_neutral_and_rejects_unknown_ids():
    adapter = build_adapter("adapter:mock-provider", provider_id="provider:mock-local")
    assert isinstance(adapter, MockProviderAdapter)
    litellm = build_adapter("adapter:litellm-proxy", api_key="", base_url="http://127.0.0.1:4000")
    assert litellm.adapter_id == "adapter:litellm-proxy"
    with pytest.raises(ValueError, match="unknown adapter"):
        build_adapter("adapter:does-not-exist")


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


def test_cursor_cli_adapter_is_shell_free_and_read_only_by_default(tmp_path: Path):
    observed = {}

    def runner(argv, **kwargs):
        observed.update(argv=argv, kwargs=kwargs)
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                {
                    "type": "result",
                    "result": "bounded audit complete",
                    "session_id": "cursor-session-1",
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                }
            ).encode(),
            b"",
        )

    result = CursorCliProviderAdapter(str(tmp_path), runner=runner).execute(
        contract(), model_name="auto"
    )
    assert observed["kwargs"]["shell"] is False
    assert "--force" not in observed["argv"]
    assert observed["kwargs"]["cwd"] == str(tmp_path)
    assert result.provider_request_id == "cursor-session-1"
    assert result.usage.input_units == 7


def test_cursor_cli_adapter_requires_explicit_mutation_admission(tmp_path: Path):
    observed = {}

    def runner(argv, **kwargs):
        observed["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, b'{"type":"result","result":"ok"}', b"")

    CursorCliProviderAdapter(str(tmp_path), allow_write=True, runner=runner).execute(
        contract(), model_name="auto"
    )
    assert "--force" in observed["argv"]


def test_cursor_cli_adapter_supports_shell_free_wsl_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    observed = {}
    monkeypatch.setenv("CURSOR_API_KEY", "cursor-duration-key")

    def runner(argv, **kwargs):
        observed.update(argv=argv, kwargs=kwargs)
        return subprocess.CompletedProcess(argv, 0, b'{"type":"result","result":"ok"}', b"")

    adapter = CursorCliProviderAdapter(
        str(tmp_path),
        executable="/home/kevin/.local/bin/cursor-agent",
        command_prefix=("wsl.exe", "-d", "Cursor-Agent-WSL1", "--"),
        runner=runner,
    )
    adapter.execute(contract(), model_name="auto")
    assert observed["argv"][:5] == [
        "wsl.exe",
        "-d",
        "Cursor-Agent-WSL1",
        "--",
        "/home/kevin/.local/bin/cursor-agent",
    ]
    assert observed["kwargs"]["shell"] is False
    wsenv = (observed["kwargs"].get("env") or {}).get("WSLENV", "")
    assert "CURSOR_API_KEY" in wsenv.split(":")


def test_cursor_cli_adapter_replays_existing_idempotent_artifact(tmp_path: Path):
    artifact = tmp_path / "pp384_cursor_cli_qualification_artifact.json"
    artifact.write_text(
        '{"idempotency_key":"pp384-cursor-cli-qualification-v1"}\n', encoding="utf-8"
    )
    calls = 0

    def runner(argv, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, b'{"type":"result","result":"mutated"}', b"")

    adapter = CursorCliProviderAdapter(str(tmp_path), allow_write=True, runner=runner)
    replay_contract = ExecutionTaskContract(
        task_id="PP-TASK-000384",
        task_class="qualification",
        required_capabilities=("code_implementation",),
        instructions="do not rewrite",
        context={
            "idempotency_key": "pp384-cursor-cli-qualification-v1",
            "artifact": "pp384_cursor_cli_qualification_artifact.json",
        },
    )
    first = adapter.execute(replay_contract, model_name="auto")
    second = adapter.execute(replay_contract, model_name="auto")
    assert calls == 0
    assert first.finish_reason == "replayed"
    assert second.finish_reason == "replayed"
    assert artifact.read_text(encoding="utf-8") == (
        '{"idempotency_key":"pp384-cursor-cli-qualification-v1"}\n'
    )


def test_cursor_cli_adapter_rejects_conflicting_idempotent_artifact(tmp_path: Path):
    artifact = tmp_path / "pp384_cursor_cli_qualification_artifact.json"
    artifact.write_text('{"idempotency_key":"other-key"}\n', encoding="utf-8")

    def runner(argv, **kwargs):
        raise AssertionError("conflicting replay must not invoke the CLI")

    adapter = CursorCliProviderAdapter(str(tmp_path), allow_write=True, runner=runner)
    replay_contract = ExecutionTaskContract(
        task_id="PP-TASK-000384",
        task_class="qualification",
        required_capabilities=("code_implementation",),
        instructions="do not rewrite",
        context={
            "idempotency_key": "pp384-cursor-cli-qualification-v1",
            "artifact": "pp384_cursor_cli_qualification_artifact.json",
        },
    )
    with pytest.raises(ProviderAdapterError, match="conflicts with idempotency key") as error:
        adapter.execute(replay_contract, model_name="auto")
    assert error.value.kind == "CONFLICTING_REPLAY"
