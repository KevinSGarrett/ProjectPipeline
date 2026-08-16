from __future__ import annotations

import subprocess
from pathlib import Path

from project_pipeline.agent_router.docker_mcp_gateway import DockerMCPGatewayAdapter


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
