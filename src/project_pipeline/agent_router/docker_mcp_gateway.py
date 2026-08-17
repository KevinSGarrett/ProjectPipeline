from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from project_pipeline.agent_router.adapters import ProviderAdapterError
from project_pipeline.upstream_contracts import docker_mcp_gateway_security_defaults

Runner = Callable[[Sequence[str], Path, float], subprocess.CompletedProcess[str]]


def _runner(argv: Sequence[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


@dataclass(frozen=True, slots=True)
class DockerMCPGatewayPlan:
    argv: tuple[str, ...]
    cwd: str


class DockerMCPGatewayAdapter:
    """Secure command adapter for Docker MCP Gateway; does not grant tool authority."""

    adapter_id = "adapter:docker-mcp-gateway"
    adapter_version = "1.0.0"

    def __init__(
        self, executable: str = "docker", *, runner: Runner = _runner, timeout_seconds: float = 60.0
    ) -> None:
        self.executable = executable
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.contract = docker_mcp_gateway_security_defaults()

    def health(self) -> Mapping[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "installed": shutil.which(self.executable) is not None,
            "upstream_id": self.contract["upstream_id"],
            "secure_defaults": self.contract["secure_defaults"],
        }

    def build_plan(
        self,
        cwd: Path,
        *,
        servers: tuple[str, ...] = (),
        tools: tuple[str, ...] = (),
        block_network: bool = True,
        dry_run: bool = True,
    ) -> DockerMCPGatewayPlan:
        defaults = self.contract["secure_defaults"]
        argv = [self.executable, "mcp", "gateway", "run"]
        argv.extend(["--transport", str(defaults["transport"])])
        argv.extend(["--cpus", str(defaults["cpus"])])
        argv.extend(["--memory", str(defaults["memory"])])
        if defaults.get("block_secrets", True):
            argv.append("--block-secrets")
        if defaults.get("verify_signatures", True):
            argv.append("--verify-signatures")
        if defaults.get("log_calls", True):
            argv.append("--log-calls")
        if block_network:
            argv.append("--block-network")
        for server in servers:
            if not server or server.startswith("-"):
                raise ValueError("server names must not be options")
            argv.extend(["--servers", server])
        for tool in tools:
            if not tool or tool.startswith("-"):
                raise ValueError("tool names must not be options")
            argv.extend(["--tools", tool])
        if dry_run:
            argv.append("--dry-run")
        return DockerMCPGatewayPlan(tuple(argv), str(cwd))

    def invoke_plan(
        self, plan: DockerMCPGatewayPlan, *, approved: bool = False
    ) -> Mapping[str, object]:
        if not approved:
            return {"state": "DRY_RUN", "argv": list(plan.argv), "cwd": plan.cwd}
        result = self.runner(plan.argv, Path(plan.cwd), self.timeout_seconds)
        if result.returncode != 0:
            raise ProviderAdapterError(
                f"Docker MCP Gateway exited {result.returncode}",
                kind="TOOL_GATEWAY_ERROR",
                retryable=True,
            )
        return {"state": "STARTED", "stdout": result.stdout}

    def invoke(
        self, tool_id: str, operation: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        if operation != "invoke":
            raise ProviderAdapterError("unlisted Docker MCP operation", kind="POLICY_DENIED")
        cwd = Path(str(arguments.get("cwd") or "."))
        approved = bool(arguments.get("approved"))
        plan = self.build_plan(
            cwd,
            servers=tuple(arguments.get("servers") or ()),
            tools=tuple(arguments.get("tools") or ()),
            dry_run=not approved,
        )
        return self.invoke_plan(plan, approved=approved)
