"""Windows OpenSSH-over-Tailscale dispatch through a fixed worker entrypoint.

Caller-controlled workspace paths are never interpolated into ``cmd /c``.
A path segment named ``pp_jobs`` is not confinement.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.confinement import ConfinementError, reject_unsafe_string
from project_pipeline.autonomy_runtime.service import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    SAFE_ENV_KEYS,
)
from project_pipeline.autonomy_runtime.windows_limits import NESTED_POOL_KEYS

XEON_MACHINE_ID = "WIN-EVSH1DN8H5O"
XEON_TAILNET_IPV4 = "100.107.207.66"
XEON_SSH_USER = "kines"
COMFY_MACHINE_ID = "COMFY-V4-CPU-01"
COMFY_TAILNET_IPV4 = "100.77.151.3"
COMFY_SSH_USER = "Windows 11"
DEFAULT_IDENTITY = Path.home() / ".ssh" / "id_ed25519"
PYTHON_NAMES = frozenset({"python", "python.exe", "python3", "python3.exe"})
SSH_CLIENT_ENV_KEYS = SAFE_ENV_KEYS | frozenset({"PROGRAMDATA"})
ALWAYS_DENIED_USERS = frozenset({"kevin"})
COMFY_DENIED_USERS = frozenset({"kevin", "kines"})
FLEET_SSH_TARGETS: Mapping[str, Mapping[str, str]] = {
    XEON_MACHINE_ID: {"host": XEON_TAILNET_IPV4, "user": XEON_SSH_USER},
    COMFY_MACHINE_ID: {"host": COMFY_TAILNET_IPV4, "user": COMFY_SSH_USER},
}
WORKER_ENTRYPOINT = ("python", "-m", "project_pipeline.autonomy_runtime.worker_entrypoint")
REMOTE_WORKER_SCRIPTS = {
    XEON_MACHINE_ID: r"C:\Users\kines\ProjectPipeline\worker\cycle20_remote_worker.py",
    COMFY_MACHINE_ID: r"C:\Users\Windows 11\ProjectPipeline\worker\cycle20_remote_worker.py",
}


def timeout_output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def default_identity_path() -> Path:
    return DEFAULT_IDENTITY


def _denied_users_for_host(host: str) -> frozenset[str]:
    if host == COMFY_TAILNET_IPV4:
        return COMFY_DENIED_USERS
    return ALWAYS_DENIED_USERS


def _machine_id_for_host(host: str) -> str:
    for machine_id, target in FLEET_SSH_TARGETS.items():
        if target["host"] == host:
            return machine_id
    return XEON_MACHINE_ID


def build_ssh_argv(
    *,
    identity: Path,
    user: str,
    host: str,
    remote_argv: list[str],
    remote_cwd: str,
    connect_timeout: int = 8,
) -> list[str]:
    denied = _denied_users_for_host(host)
    if user.lower() in denied:
        raise ValueError(f"do not SSH as {user.lower()}@ on {host}")
    if not identity.is_file():
        raise ValueError("ssh identity file is missing")
    if not remote_argv or any(not item or "\x00" in item for item in remote_argv):
        raise ValueError("remote argv must be a non-empty argument array")
    if not remote_command_allowed(tuple(remote_argv)):
        raise ValueError("remote argv is not allowlisted")
    try:
        reject_unsafe_string(remote_cwd, field="workspace")
    except ConfinementError as error:
        raise ValueError(str(error)) from error
    machine_id = _machine_id_for_host(host)
    worker_script = REMOTE_WORKER_SCRIPTS.get(machine_id)
    remote_worker = ("python", worker_script) if worker_script else WORKER_ENTRYPOINT
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
        "-l",
        user,
        host,
        *remote_worker,
    ]


def remote_command_allowed(argv: tuple[str, ...]) -> bool:
    if not argv:
        return False
    name = Path(argv[0]).name.lower()
    if name == "hostname":
        return len(argv) == 1
    if name not in PYTHON_NAMES:
        return False
    if len(argv) == 2 and argv[1] in {"-V", "--version"}:
        return True
    if (
        len(argv) >= 3
        and argv[1] == "-m"
        and argv[2] == "project_pipeline.autonomy_runtime.worker_entrypoint"
    ):
        return True
    if len(argv) >= 2 and not str(argv[1]).startswith("-"):
        posix = argv[1].replace("\\", "/")
        if "pp_jobs" in posix.split("/"):
            return False
        if not posix.lower().endswith(".py") or ".." in posix:
            return False
        for item in argv[2:]:
            try:
                reject_unsafe_string(item, field="argv")
            except ConfinementError:
                return False
        return True
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
        machine_id: str | None = None,
    ) -> None:
        self.host = host
        self.user = user
        self.machine_id = machine_id or _machine_id_for_host(host)
        self.identity = identity or default_identity_path()
        self.connect_timeout = connect_timeout
        self.runner = runner

    @classmethod
    def for_machine(
        cls,
        machine_id: str,
        *,
        identity: Path | None = None,
        connect_timeout: int = 8,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> SshDispatchAdapter:
        target = FLEET_SSH_TARGETS.get(machine_id)
        if target is None:
            raise ValueError(f"unknown fleet ssh target: {machine_id}")
        return cls(
            host=target["host"],
            user=target["user"],
            machine_id=machine_id,
            identity=identity,
            connect_timeout=connect_timeout,
            runner=runner,
        )

    def execute(
        self,
        *,
        command: list[str],
        working_directory: Path,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        extra_env: dict[str, str] | None = None,
        job_handle: int | None = None,
    ) -> dict[str, Any]:
        extra = extra_env or {}
        if extra and any(key not in NESTED_POOL_KEYS for key in extra):
            raise ValueError("remote dispatch does not accept extra environment values")
        del job_handle
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
        runner = self.runner or subprocess.run
        stdin_payload = json.dumps(
            {
                "argv": command,
                "workspace": str(working_directory),
                "host_id": self.machine_id,
                "nested_env": extra,
                "job_id": extra.get("PP_JOB_ID") if extra else None,
            },
            sort_keys=True,
        )
        try:
            completed = runner(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
                env=env,
                input=stdin_payload,
            )
            raw_stdout = completed.stdout or ""
            raw_stderr = completed.stderr or ""
            timed_out = False
            exit_code = completed.returncode
        except TypeError:
            # Injected test runners may not accept input=
            try:
                completed = runner(
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
                raw_stdout = timeout_output_text(error.stdout or error.output)
                raw_stderr = timeout_output_text(error.stderr)
                timed_out = True
                exit_code = 124
        except subprocess.TimeoutExpired as error:
            raw_stdout = timeout_output_text(error.stdout or error.output)
            raw_stderr = timeout_output_text(error.stderr)
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
            "machine_id": self.machine_id,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "output_truncated": len(raw_stdout) > max_output_bytes
            or len(raw_stderr) > max_output_bytes,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        }
        payload["payload_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return payload
