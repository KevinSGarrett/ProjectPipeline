from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from project_pipeline.agent_router import GovernedToolBoundary, ProviderAdapterError
from project_pipeline.agent_router.docker_mcp_gateway import DockerMCPGatewayAdapter
from project_pipeline.agent_router.registry import load_agent_registry


def test_docker_mcp_gateway_plan_applies_reviewed_secure_defaults(tmp_path: Path) -> None:
    adapter = DockerMCPGatewayAdapter()
    plan = adapter.build_plan(tmp_path, servers=("github",), tools=("issues.read",))
    argv = plan.argv
    assert argv[:4] == ("docker", "mcp", "gateway", "run")
    assert "--block-secrets" in argv
    assert "--verify-signatures" in argv
    assert "--block-network" in argv
    assert "--dry-run" in argv
    assert argv[argv.index("--transport") + 1] == "stdio"
    assert adapter.invoke_plan(plan)["state"] == "DRY_RUN"


def test_docker_mcp_gateway_execution_requires_explicit_approval(tmp_path: Path) -> None:
    calls = []

    def runner(argv, cwd, timeout):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "started", "")

    adapter = DockerMCPGatewayAdapter(runner=runner)
    plan = adapter.build_plan(tmp_path, dry_run=True)
    assert adapter.invoke_plan(plan, approved=True)["state"] == "STARTED"
    assert calls and calls[0][0:4] == ("docker", "mcp", "gateway", "run")


def test_docker_mcp_tool_is_registered_and_denied_without_mutation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_agent_registry(root)
    tool = next(item for item in registry.tools if item.tool_id == "tool:docker-mcp-gateway")
    assert tool.mutating is True
    assert tool.qualification.value == "QUARANTINED"
    boundary = GovernedToolBoundary(
        {tool.tool_id: tool},
        {tool.adapter_id: DockerMCPGatewayAdapter()},
        workspace_root=tmp_path,
        allowed_operations={tool.tool_id: {"invoke"}},
    )
    with pytest.raises(ProviderAdapterError, match="mutation intent"):
        boundary.invoke(tool.tool_id, "invoke", {"cwd": str(tmp_path)})
    result = boundary.invoke(tool.tool_id, "invoke", {"cwd": str(tmp_path)}, mutate=True)
    assert result["result"]["state"] == "DRY_RUN"
