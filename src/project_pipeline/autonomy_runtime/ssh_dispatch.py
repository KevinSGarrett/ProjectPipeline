"""Windows OpenSSH-over-Tailscale dispatch through the existing runtime port.

This is not Tailscale SSH-server. The adapter never copies ``.env`` files or
prints identity-file bytes. SWE-ReX is unused: local subprocess argv plus ssh.exe
are sufficient.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.service import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    SAFE_ENV_KEYS,
)

XEON_TAILNET_IPV4 = "100.107.207.66"
XEON_SSH_USER = "kines"
DEFAULT_IDENTITY = Path.home() / ".ssh" / "id_ed25519"
SHELL_METATOKENS = frozenset({";", "|", "&", "`", "$", "\n", "\r"})
PYTHON_NAMES = frozenset({"python", "python.exe", "python3", "python3.exe"})
SSH_CLIENT_ENV_KEYS = SAFE_ENV_KEYS | frozenset({"PROGRAMDATA"})


def default_identity_path() -> Path:
    return DEFAULT_IDENTITY


def build_ssh_argv(
    *,
    identity: Path,
    user: str,
    host: str,
    remote_argv: list[str],
    remote_cwd: str,
    connect_timeout: int = 8,
) -> list[str]:
    if user.lower() == "kevin":
        raise ValueError("do not SSH as kevin@ on WIN-EVSH1DN8H5O")
    if not identity.is_file():
        raise ValueError("ssh identity file is missing")
    if not remote_argv or any(not item or "\x00" in item for item in remote_argv):
        raise ValueError("remote argv must be a non-empty argument array")
    if not remote_command_allowed(tuple(remote_argv)):
        raise ValueError("remote argv is not allowlisted")
    remote_command = f"cd /d {remote_cwd} && {subprocess.list2cmdline(remote_argv)}"
    return [
        "ssh",
        "-i",
        str(identity),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        f"{user}@{host}",
        "cmd",
        "/c",
        remote_command,
    ]


def remote_command_allowed(argv: tuple[str, ...]) -> bool:
    if not argv:
        return False
    name = Path(argv[0]).name.lower()
    if name == "hostname" and len(argv) == 1:
        return True
    if name in PYTHON_NAMES and len(argv) == 2:
        remote_path = Path(argv[1])
        return remote_path.suffix.lower() == ".py" and "pp_jobs" in remote_path.parts
    if name in PYTHON_NAMES and len(argv) >= 3 and argv[1] == "-c":
        script = argv[2]
        return not any(token in script for token in SHELL_METATOKENS)
    return False


class SshDispatchAdapter:
    """Dispatch one allowlisted argv over OpenSSH. Does not share controller credentials."""

    remote_host = True

    def __init__(
        self,
        *,
        host: str = XEON_TAILNET_IPV4,
        user: str = XEON_SSH_USER,
        identity: Path | None = None,
        connect_timeout: int = 8,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.host = host
        self.user = user
        self.identity = identity or default_identity_path()
        self.connect_timeout = connect_timeout
        self.runner = runner

    def execute(
        self,
        *,
        command: list[str],
        working_directory: Path,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if extra_env:
            raise ValueError("remote dispatch does not accept extra environment values")
        argv = build_ssh_argv(
            identity=self.identity,
            user=self.user,
            host=self.host,
            remote_argv=command,
            remote_cwd=str(working_directory),
            connect_timeout=self.connect_timeout,
        )
        allowed = {item.upper() for item in SSH_CLIENT_ENV_KEYS}
        env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        try:
            if self.runner is not None:
                completed = self.runner(
                    argv,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                    env=env,
                )
            else:
                completed = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                    env=env,
                )
            raw_stdout = completed.stdout or ""
            raw_stderr = completed.stderr or ""
            timed_out = False
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as error:
            raw_stdout = error.stdout.decode("utf-8", errors="replace") if error.stdout else ""
            raw_stderr = error.stderr.decode("utf-8", errors="replace") if error.stderr else ""
            timed_out = True
            exit_code = 124
        stdout = raw_stdout[:max_output_bytes]
        stderr = raw_stderr[:max_output_bytes]
        payload = {
            "command": command,
            "working_directory": str(working_directory),
            "transport": "openssh_tailscale",
            "host": self.host,
            "user": self.user,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "output_truncated": len(raw_stdout) > max_output_bytes or len(raw_stderr) > max_output_bytes,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        }
        payload["payload_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return payload
