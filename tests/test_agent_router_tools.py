from pathlib import Path

import pytest

from project_pipeline.agent_router import (
    GovernedToolBoundary,
    MockToolAdapter,
    ProviderAdapterError,
)
from project_pipeline.domain.agents import ToolSpec


def _boundary(tmp_path: Path, *, mutating: bool = False) -> GovernedToolBoundary:
    spec = ToolSpec(
        tool_id="tool:mock-safe",
        adapter_id="adapter:mock-tool",
        version="1",
        capabilities=("routine_reasoning",),
        mutating=mutating,
        required_authority_scope=("read", "write") if mutating else ("read",),
    )
    return GovernedToolBoundary(
        {spec.tool_id: spec},
        {"adapter:mock-tool": MockToolAdapter({spec.tool_id: {"read", "write"}})},
        workspace_root=tmp_path,
        allowed_operations={spec.tool_id: {"read", "write"}},
    )


def test_governed_tool_denies_unlisted_traversal_shell_and_conflict(tmp_path: Path):
    boundary = _boundary(tmp_path)
    ok = boundary.invoke("tool:mock-safe", "read", {"path": str(tmp_path / "note.txt")})
    assert ok["receipt_sha256"]
    with pytest.raises(ProviderAdapterError, match="unlisted"):
        boundary.invoke("tool:missing", "read", {})
    with pytest.raises(ProviderAdapterError, match="not allowed"):
        boundary.invoke("tool:mock-safe", "delete", {})
    with pytest.raises(ProviderAdapterError, match="shell"):
        boundary.invoke("tool:mock-safe", "read", {"cmd": "echo hi; rm -rf /"})
    with pytest.raises(ProviderAdapterError, match="escapes"):
        boundary.invoke("tool:mock-safe", "read", {"path": str(tmp_path / ".." / "outside.txt")})
    with pytest.raises(ProviderAdapterError, match="conflicting"):
        boundary.invoke("tool:mock-safe", "read", {}, claimed_tool_id="tool:other")


def test_governed_tool_requires_explicit_mutation_intent(tmp_path: Path):
    boundary = _boundary(tmp_path, mutating=True)
    with pytest.raises(ProviderAdapterError, match="mutation intent"):
        boundary.invoke("tool:mock-safe", "write", {"value": "x"})
    result = boundary.invoke("tool:mock-safe", "write", {"value": "x"}, mutate=True)
    assert result["result"]["outcome"] == "MOCK_VERIFIED"
