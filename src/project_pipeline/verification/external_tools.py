from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class VerificationToolUnavailable(RuntimeError):
    """Raised when an optional verification executable is not installed."""


@dataclass(frozen=True, slots=True)
class ExternalVerificationCommand:
    tool: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int = 300

    def run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.argv,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
            shell=False,
        )


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise VerificationToolUnavailable(
            f"optional verification executable is unavailable: {name}"
        )
    return path


class MutmutAdapter:
    """Optional mutation runner; Project Pipeline owns pass/fail interpretation."""

    def build(self, root: Path) -> ExternalVerificationCommand:
        binary = _require_binary("mutmut")
        return ExternalVerificationCommand("mutmut", (binary, "run"), root.resolve(), 1800)


class SchemathesisAdapter:
    """Optional OpenAPI property runner with explicit local schema/base URL."""

    def build(self, root: Path, *, schema: Path, base_url: str) -> ExternalVerificationCommand:
        schema = schema.resolve()
        if root.resolve() not in schema.parents and schema != root.resolve():
            raise ValueError("Schemathesis schema must remain inside the project root")
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("Pass 16 Schemathesis adapter is restricted to local test servers")
        binary = _require_binary("schemathesis")
        return ExternalVerificationCommand(
            "schemathesis",
            (binary, "run", str(schema), "--base-url", base_url),
            root.resolve(),
            900,
        )


class LighthouseCIAdapter:
    """Optional Lighthouse CI boundary restricted to a local verification URL."""

    def build(self, root: Path, *, url: str) -> ExternalVerificationCommand:
        binary = _require_binary("lhci")
        if not url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("Lighthouse CI verification is restricted to local targets")
        return ExternalVerificationCommand(
            "lighthouse-ci",
            (binary, "collect", "--url", url, "--numberOfRuns", "3"),
            root.resolve(),
            900,
        )


class PlaywrightMCPProfile:
    """Describes an optional Playwright MCP process without auto-installing packages."""

    binary_name = "playwright-mcp"

    def command(self, root: Path) -> ExternalVerificationCommand:
        binary = _require_binary(self.binary_name)
        return ExternalVerificationCommand(
            "playwright-mcp",
            (binary, "--headless"),
            root.resolve(),
            300,
        )


class AgentBrowserProfile:
    """Optional agent-browser boundary. It cannot certify visual correctness."""

    binary_name = "agent-browser"

    def command(self, root: Path, *args: str) -> ExternalVerificationCommand:
        binary = _require_binary(self.binary_name)
        forbidden = {"--headed-server", "--remote-debugging-port"}
        if any(arg in forbidden for arg in args):
            raise ValueError("unsafe agent-browser process-control flag")
        return ExternalVerificationCommand(
            "agent-browser",
            (binary, *args),
            root.resolve(),
            300,
        )


class ToxiproxyProfile:
    """Optional network-fault runtime. Pass 16 uses deterministic in-process faults if absent."""

    def server_path(self) -> str:
        return _require_binary("toxiproxy-server")


class AxeCoreProfile:
    """axe-core must be supplied as a local reviewed bundle; remote CDN execution is forbidden."""

    def validate_bundle(self, root: Path, bundle_path: Path) -> Path:
        root = root.resolve()
        path = bundle_path.resolve()
        if root not in path.parents:
            raise ValueError("axe-core bundle must be repository-local")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
