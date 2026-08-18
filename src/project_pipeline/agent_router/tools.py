from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.agent_router.adapters import ProviderAdapterError, ToolAdapter
from project_pipeline.domain.agents import ToolSpec

_SHELL_UNSAFE = re.compile(r"[;&|`$<>\n]")
_TRAVERSAL = re.compile(r"(^|[\\/])\.\.([\\/]|$)")


class GovernedToolBoundary:
    """Deny-by-default tool invocation with path, secret, and mutation guards."""

    def __init__(
        self,
        tools: Mapping[str, ToolSpec],
        adapters: Mapping[str, ToolAdapter],
        *,
        workspace_root: Path,
        allowed_operations: Mapping[str, set[str]] | None = None,
        timeout_seconds: float = 30.0,
        max_output_bytes: int = 65_536,
    ) -> None:
        self.tools = dict(tools)
        self.adapters = dict(adapters)
        self.workspace_root = workspace_root.resolve()
        self.allowed_operations = allowed_operations or {
            tool_id: set(spec.required_authority_scope) or {"read"}
            for tool_id, spec in self.tools.items()
        }
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def invoke(
        self,
        tool_id: str,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        mutate: bool = False,
        claimed_tool_id: str | None = None,
    ) -> dict[str, Any]:
        if claimed_tool_id is not None and claimed_tool_id != tool_id:
            raise ProviderAdapterError("conflicting tool claim", kind="POLICY_DENIED")
        spec = self.tools.get(tool_id)
        if spec is None:
            raise ProviderAdapterError("unlisted tool", kind="POLICY_DENIED")
        allowed = self.allowed_operations.get(tool_id, set())
        if operation not in allowed:
            raise ProviderAdapterError("tool operation not allowed", kind="POLICY_DENIED")
        if spec.mutating and not mutate:
            raise ProviderAdapterError(
                "mutating tool requires explicit mutation intent", kind="POLICY_DENIED"
            )
        self._reject_unsafe_arguments(arguments)
        adapter = self.adapters.get(spec.adapter_id)
        if adapter is None:
            raise ProviderAdapterError("tool adapter is not registered", kind="POLICY_DENIED")
        result = adapter.invoke(tool_id, operation, arguments)
        encoded = json.dumps(result, sort_keys=True, default=str).encode()
        if len(encoded) > self.max_output_bytes:
            raise ProviderAdapterError("tool output exceeded bound", kind="POLICY_DENIED")
        return {
            "tool_id": tool_id,
            "operation": operation,
            "result": result,
            "receipt_sha256": hashlib.sha256(encoded).hexdigest(),
            "timeout_seconds": self.timeout_seconds,
            "observed_at_utc": datetime.now(UTC).isoformat(),
        }

    def _reject_unsafe_arguments(self, arguments: Mapping[str, Any]) -> None:
        for key, value in arguments.items():
            if not isinstance(value, str):
                continue
            if _SHELL_UNSAFE.search(value):
                raise ProviderAdapterError(
                    "shell metacharacters are not allowed", kind="POLICY_DENIED"
                )
            if key.endswith("path") or _TRAVERSAL.search(value) or "\\" in value or "/" in value:
                self._assert_contained(value)

    def _assert_contained(self, raw: str) -> None:
        candidate = Path(raw)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.workspace_root / candidate).resolve()
        )
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as error:
            raise ProviderAdapterError(
                "path escapes tool workspace", kind="POLICY_DENIED"
            ) from error
