from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any, cast

from project_pipeline.agent_router.adapters import ProviderAdapterError
from project_pipeline.domain.agents import (
    ExecutionTaskContract,
    NormalizedUsage,
    ProviderInvocationResult,
)
from project_pipeline.upstream_contracts import pydantic_ai_provider_compatibility

AgentFactory = Callable[..., Any]


class PydanticAIProviderAdapter:
    """Optional typed advisory-agent adapter using Pydantic AI when installed."""

    adapter_id = "adapter:pydantic-ai"
    adapter_version = "1.0.0"

    def __init__(self, *, agent_factory: AgentFactory | None = None) -> None:
        self._agent_factory = agent_factory
        self._compatibility = pydantic_ai_provider_compatibility()

    def _factory(self) -> AgentFactory:
        if self._agent_factory is not None:
            return self._agent_factory
        try:
            return cast(AgentFactory, import_module("pydantic_ai").Agent)
        except (ImportError, AttributeError) as error:
            raise ProviderAdapterError(
                "Pydantic AI is not installed", kind="DEPENDENCY_UNAVAILABLE"
            ) from error

    def health(self) -> Mapping[str, Any]:
        try:
            self._factory()
            installed = True
        except ProviderAdapterError:
            installed = False
        return {
            "adapter_id": self.adapter_id,
            "installed": installed,
            "upstream_id": self._compatibility["upstream_id"],
            "source_revision": self._compatibility["source_revision"],
        }

    def cancel(self, operation_id: str) -> bool:
        return False

    def checkpoint(self, operation_id: str) -> Mapping[str, Any]:
        return {"operation_id": operation_id, "checkpoint_supported": False}

    def execute(
        self, contract: ExecutionTaskContract, *, model_name: str
    ) -> ProviderInvocationResult:
        kwargs: dict[str, Any] = {}
        if contract.output_schema is not None:
            # Keep provider/framework-specific typing outside the universal task contract.
            kwargs["instructions"] = (
                "Return output that conforms to the supplied Project Pipeline schema."
            )
        agent = self._factory()(model_name, **kwargs)
        try:
            result = agent.run_sync(contract.instructions)
        except Exception as error:
            raise ProviderAdapterError(
                f"Pydantic AI invocation failed: {type(error).__name__}",
                kind="FRAMEWORK_ERROR",
                retryable=True,
                provider_state="DEGRADED",
            ) from error
        output = result.output
        if hasattr(output, "model_dump"):
            normalized = output.model_dump(mode="json")
        elif isinstance(output, dict):
            normalized = output
        elif isinstance(output, str):
            normalized = {"text": output}
        else:
            try:
                normalized = json.loads(json.dumps(output, default=str))
                if not isinstance(normalized, dict):
                    normalized = {"value": normalized}
            except Exception:
                normalized = {"value": str(output)}
        usage_obj = getattr(result, "usage", lambda: None)()
        usage = NormalizedUsage()
        if usage_obj is not None:
            usage = NormalizedUsage(
                input_units=int(getattr(usage_obj, "input_tokens", 0) or 0),
                output_units=int(getattr(usage_obj, "output_tokens", 0) or 0),
                cached_input_units=int(getattr(usage_obj, "cache_read_tokens", 0) or 0),
                request_count=int(getattr(usage_obj, "requests", 1) or 1),
            )
        return ProviderInvocationResult(
            provider_id="provider:pydantic-ai",
            model_id=model_name,
            output=normalized,
            usage=usage,
            evidence_references=("UPSTREAM-086",),
        )
