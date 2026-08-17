from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from project_pipeline.domain.agents import (
    ExecutionTaskContract,
    NormalizedUsage,
    ProviderInvocationResult,
)


class ProviderAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: str = "PROVIDER_ERROR",
        retryable: bool = False,
        provider_state: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.provider_state = provider_state


class ProviderAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult: ...
    def health(self) -> Mapping[str, Any]: ...
    def cancel(self, operation_id: str) -> bool: ...
    def checkpoint(self, operation_id: str) -> Mapping[str, Any]: ...


Transport = Callable[
    [str, str, Mapping[str, str], bytes, float], tuple[int, Mapping[str, str], bytes]
]


def urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float
) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url=url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), dict(error.headers.items()), error.read()


@dataclass
class BaseHttpProviderAdapter:
    adapter_id: str
    adapter_version: str
    api_key: str
    base_url: str
    timeout_seconds: float = 120.0
    transport: Transport = urllib_transport

    def health(self) -> Mapping[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "configured": bool(self.api_key),
            "base_url": self.base_url,
        }

    def cancel(self, operation_id: str) -> bool:
        return False

    def checkpoint(self, operation_id: str) -> Mapping[str, Any]:
        return {"operation_id": operation_id, "checkpoint_supported": False}

    def _post(
        self, path: str, headers: Mapping[str, str], payload: Mapping[str, Any]
    ) -> tuple[Any, Mapping[str, str]]:
        try:
            status, response_headers, body = self.transport(
                "POST",
                self.base_url.rstrip("/") + path,
                headers,
                json.dumps(payload).encode(),
                self.timeout_seconds,
            )
        except ProviderAdapterError:
            raise
        except Exception as error:
            raise ProviderAdapterError(
                f"hosted provider outcome is unknown: {error}",
                kind="UNKNOWN_OUTCOME",
                retryable=True,
                provider_state="UNAVAILABLE",
            ) from error
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception as error:
            raise ProviderAdapterError(
                f"malformed JSON response: {error}", kind="MALFORMED_OUTPUT"
            ) from error
        if status >= 400:
            retry = status in {408, 409, 429} or status >= 500
            raise ProviderAdapterError(
                f"provider HTTP {status}",
                kind="RATE_LIMIT" if status == 429 else "HTTP_ERROR",
                retryable=retry,
                provider_state="RATE_LIMITED" if status == 429 else "UNAVAILABLE",
            )
        return data, response_headers


class OpenAIResponsesAdapter(BaseHttpProviderAdapter):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com",
        transport: Transport = urllib_transport,
        timeout_seconds: float = 120.0,
    ):
        super().__init__(
            "adapter:openai-responses", "1.0.0", api_key, base_url, timeout_seconds, transport
        )

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        payload = {"model": model_name, "input": contract.instructions, "store": False}
        if contract.output_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "project_pipeline_result",
                    "schema": contract.output_schema,
                    "strict": True,
                }
            }
        data, _ = self._post(
            "/v1/responses",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload,
        )
        text = data.get("output_text")
        if text is None:
            parts = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            parts.append(content.get("text", ""))
            text = "".join(parts)
        usage = data.get("usage") or {}
        return ProviderInvocationResult(
            provider_id="provider:openai-api",
            output={"text": text, "raw_status": data.get("status")},
            usage=NormalizedUsage(
                input_units=int(usage.get("input_tokens", 0) or 0),
                output_units=int(usage.get("output_tokens", 0) or 0),
                cached_input_units=int(
                    ((usage.get("input_tokens_details") or {}).get("cached_tokens", 0)) or 0
                ),
            ),
            provider_request_id=data.get("id"),
            finish_reason=data.get("status"),
        )


class AnthropicMessagesAdapter(BaseHttpProviderAdapter):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.anthropic.com",
        transport: Transport = urllib_transport,
        timeout_seconds: float = 120.0,
    ):
        super().__init__(
            "adapter:anthropic-messages", "1.0.0", api_key, base_url, timeout_seconds, transport
        )

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        payload = {
            "model": model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": contract.instructions}],
        }
        data, _ = self._post(
            "/v1/messages",
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload,
        )
        text = "".join(
            item.get("text", "") for item in data.get("content", []) if item.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return ProviderInvocationResult(
            provider_id="provider:anthropic-api",
            output={"text": text},
            usage=NormalizedUsage(
                input_units=int(usage.get("input_tokens", 0) or 0),
                output_units=int(usage.get("output_tokens", 0) or 0),
            ),
            provider_request_id=data.get("id"),
            finish_reason=data.get("stop_reason"),
        )


class GeminiGenerateContentAdapter(BaseHttpProviderAdapter):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://generativelanguage.googleapis.com",
        transport: Transport = urllib_transport,
        timeout_seconds: float = 120.0,
    ):
        super().__init__(
            "adapter:gemini-generate-content",
            "1.0.0",
            api_key,
            base_url,
            timeout_seconds,
            transport,
        )

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        payload = {"contents": [{"role": "user", "parts": [{"text": contract.instructions}]}]}
        data, _ = self._post(
            f"/v1beta/models/{model_name}:generateContent",
            {"x-goog-api-key": self.api_key, "content-type": "application/json"},
            payload,
        )
        candidates = data.get("candidates") or []
        text = ""
        finish = None
        if candidates:
            finish = candidates[0].get("finishReason")
            text = "".join(
                part.get("text", "")
                for part in (candidates[0].get("content") or {}).get("parts", [])
                if "text" in part
            )
        usage = data.get("usageMetadata") or {}
        return ProviderInvocationResult(
            provider_id="provider:gemini-api",
            output={"text": text},
            usage=NormalizedUsage(
                input_units=int(usage.get("promptTokenCount", 0) or 0),
                output_units=int(usage.get("candidatesTokenCount", 0) or 0),
                cached_input_units=int(usage.get("cachedContentTokenCount", 0) or 0),
            ),
            finish_reason=finish,
        )


class LiteLLMProxyAdapter(BaseHttpProviderAdapter):
    """Stable LiteLLM proxy boundary using the OpenAI-compatible chat API.

    Project Pipeline retains capability routing and policy authority; LiteLLM is
    an optional transport/gateway implementation only.
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str = "http://127.0.0.1:4000",
        transport: Transport = urllib_transport,
        timeout_seconds: float = 120.0,
    ) -> None:
        super().__init__(
            "adapter:litellm-proxy", "1.0.0", api_key, base_url, timeout_seconds, transport
        )

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": contract.instructions}],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data, _ = self._post("/v1/chat/completions", headers, payload)
        choices = data.get("choices") or []
        text = ""
        finish = None
        if choices:
            choice = choices[0]
            finish = choice.get("finish_reason")
            message = choice.get("message") or {}
            text = message.get("content") or ""
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        return ProviderInvocationResult(
            provider_id="provider:litellm-proxy",
            model_id=model_name,
            output={"text": text},
            usage=NormalizedUsage(
                input_units=int(usage.get("prompt_tokens", 0) or 0),
                output_units=int(usage.get("completion_tokens", 0) or 0),
                cached_input_units=int(details.get("cached_tokens", 0) or 0),
            ),
            provider_request_id=data.get("id"),
            finish_reason=finish,
            evidence_references=("UPSTREAM-012",),
        )


class LocalProcessProviderAdapter:
    adapter_id = "adapter:local-json-process"
    adapter_version = "1.0.0"

    def __init__(self, argv: tuple[str, ...], *, timeout_seconds: float = 120.0) -> None:
        if not argv or any(not str(x) for x in argv):
            raise ValueError("argv must be non-empty")
        self.argv = argv
        self.timeout_seconds = timeout_seconds

    def health(self) -> Mapping[str, Any]:
        return {"adapter_id": self.adapter_id, "configured": True, "argv0": self.argv[0]}

    def cancel(self, operation_id: str) -> bool:
        return False

    def checkpoint(self, operation_id: str) -> Mapping[str, Any]:
        return {"operation_id": operation_id, "checkpoint_supported": False}

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        payload = json.dumps(
            {"model": model_name, "task": contract.model_dump(mode="json")}
        ).encode()
        try:
            result = subprocess.run(
                self.argv,
                input=payload,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ProviderAdapterError(
                "local provider timed out",
                kind="TIMEOUT",
                retryable=True,
                provider_state="DEGRADED",
            ) from error
        if result.returncode < 0:
            raise ProviderAdapterError(
                f"local provider process was lost: {result.returncode}",
                kind="PROCESS_LOSS",
                retryable=False,
                provider_state="UNAVAILABLE",
            )
        if result.returncode != 0:
            raise ProviderAdapterError(
                f"local provider exited {result.returncode}",
                kind="PROCESS_ERROR",
                retryable=True,
                provider_state="DEGRADED",
            )
        try:
            data = json.loads(result.stdout.decode())
        except Exception as error:
            raise ProviderAdapterError(
                f"local provider returned malformed JSON: {error}", kind="MALFORMED_OUTPUT"
            ) from error
        if not isinstance(data, dict) or "output" not in data:
            raise ProviderAdapterError(
                "local provider response requires output object", kind="MALFORMED_OUTPUT"
            )
        return ProviderInvocationResult(
            provider_id="provider:local-process",
            model_id=model_name,
            output=data["output"]
            if isinstance(data["output"], dict)
            else {"value": data["output"]},
            usage=NormalizedUsage.model_validate(data.get("usage") or {}),
            provider_request_id=data.get("request_id"),
            finish_reason=data.get("finish_reason"),
        )


class CursorCliProviderAdapter:
    """Governed Cursor Agent CLI boundary.

    Registry configuration keeps this adapter quarantined until representative
    qualification is recorded. It never invokes a shell and enables file writes
    only when the controlling caller explicitly admits a mutating execution.
    """

    adapter_id = "adapter:cursor-cli"
    adapter_version = "1.0.0"

    def __init__(
        self,
        workspace: str,
        *,
        executable: str | None = None,
        allow_write: bool = False,
        timeout_seconds: float = 3600.0,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        if not workspace.strip():
            raise ValueError("workspace must be non-empty")
        self.workspace = os.path.abspath(workspace)
        self.executable = executable or ("agent" if shutil.which("agent") else "cursor-agent")
        self.allow_write = allow_write
        self.timeout_seconds = timeout_seconds
        self.runner = runner

    def health(self) -> Mapping[str, Any]:
        resolved = shutil.which(self.executable)
        return {
            "adapter_id": self.adapter_id,
            "configured": resolved is not None and os.path.isdir(self.workspace),
            "executable": resolved,
            "workspace": self.workspace,
            "allow_write": self.allow_write,
        }

    def cancel(self, operation_id: str) -> bool:
        return False

    def checkpoint(self, operation_id: str) -> Mapping[str, Any]:
        return {
            "operation_id": operation_id,
            "checkpoint_supported": True,
            "resume_command": f"{self.executable} --resume={operation_id}",
        }

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        argv = [
            self.executable,
            "--print",
            "--output-format",
            "json",
            "--model",
            model_name,
        ]
        if self.allow_write:
            argv.append("--force")
        prompt = json.dumps(
            {
                "project_pipeline_execution_contract": contract.model_dump(mode="json"),
                "instruction": (
                    "Execute only this bounded contract. Repository rules and "
                    "ProjectPipeline deterministic authority remain controlling."
                ),
            },
            sort_keys=True,
        ).encode("utf-8")
        try:
            result = self.runner(
                argv,
                input=prompt,
                capture_output=True,
                cwd=self.workspace,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except FileNotFoundError as error:
            raise ProviderAdapterError(
                "Cursor Agent CLI is not installed",
                kind="UNAVAILABLE",
                provider_state="UNAVAILABLE",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ProviderAdapterError(
                "Cursor Agent CLI timed out",
                kind="TIMEOUT",
                retryable=True,
                provider_state="DEGRADED",
            ) from error
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ProviderAdapterError(
                f"Cursor Agent CLI exited {result.returncode}: {detail[:500]}",
                kind="PROCESS_ERROR",
                retryable=False,
                provider_state="DEGRADED",
            )
        try:
            data = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderAdapterError(
                f"Cursor Agent CLI returned malformed JSON: {error}",
                kind="MALFORMED_OUTPUT",
            ) from error
        if not isinstance(data, dict) or data.get("type") not in {None, "result"}:
            raise ProviderAdapterError(
                "Cursor Agent CLI response is not a result object",
                kind="MALFORMED_OUTPUT",
            )
        raw_usage = data.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        text = data.get("result") or data.get("text") or data.get("message") or ""
        return ProviderInvocationResult(
            provider_id="provider:cursor-cli",
            model_id=model_name,
            output={"text": str(text), "response": data},
            usage=NormalizedUsage(
                input_units=int(usage.get("input_tokens", 0) or 0),
                output_units=int(usage.get("output_tokens", 0) or 0),
                cached_input_units=int(usage.get("cached_input_tokens", 0) or 0),
                cost_microunits=(
                    int(usage["cost_microunits"])
                    if usage.get("cost_microunits") is not None
                    else None
                ),
            ),
            provider_request_id=data.get("session_id") or data.get("request_id"),
            finish_reason="completed",
        )


class MockProviderAdapter:
    adapter_id = "adapter:mock-provider"
    adapter_version = "1.0.0"

    def __init__(
        self, provider_id: str, outcomes: list[ProviderInvocationResult | Exception] | None = None
    ):
        self.provider_id = provider_id
        self.outcomes = list(outcomes or [])

    def health(self) -> Mapping[str, Any]:
        return {"adapter_id": self.adapter_id, "configured": True, "provider_id": self.provider_id}

    def cancel(self, operation_id: str) -> bool:
        return True

    def checkpoint(self, operation_id: str) -> Mapping[str, Any]:
        return {"operation_id": operation_id, "checkpoint_supported": True}

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        if self.outcomes:
            item = self.outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return ProviderInvocationResult(
            provider_id=self.provider_id,
            model_id=model_name,
            output={"text": f"mock:{contract.task_id}"},
            usage=NormalizedUsage(),
        )


def build_adapter(adapter_id: str, **kwargs: Any) -> ProviderAdapter:
    factories: dict[str, type] = {
        "adapter:openai-responses": OpenAIResponsesAdapter,
        "adapter:anthropic-messages": AnthropicMessagesAdapter,
        "adapter:gemini-generate-content": GeminiGenerateContentAdapter,
        "adapter:litellm-proxy": LiteLLMProxyAdapter,
        "adapter:local-json-process": LocalProcessProviderAdapter,
        "adapter:mock-provider": MockProviderAdapter,
    }
    try:
        from project_pipeline.agent_router.pydantic_ai_adapter import PydanticAIProviderAdapter

        factories["adapter:pydantic-ai"] = PydanticAIProviderAdapter
    except Exception as error:
        _optional_adapter_error = str(error)
        del _optional_adapter_error
    factory = factories.get(adapter_id)
    if factory is None:
        raise ValueError(f"unknown adapter: {adapter_id}")
    return factory(**kwargs)


class ToolAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def invoke(
        self, tool_id: str, operation: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class MockToolAdapter:
    adapter_id = "adapter:mock-tool"
    adapter_version = "1.0.0"

    def __init__(self, allowed_operations: Mapping[str, set[str]] | None = None) -> None:
        self.allowed_operations = allowed_operations or {}

    def invoke(
        self, tool_id: str, operation: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if operation not in self.allowed_operations.get(tool_id, set()):
            raise ProviderAdapterError("tool operation not allowed", kind="POLICY_DENIED")
        return {
            "tool_id": tool_id,
            "operation": operation,
            "arguments": dict(arguments),
            "outcome": "MOCK_VERIFIED",
        }
