"""Windows OpenSSH-over-Tailscale dispatch through a fixed worker entrypoint.

Caller-controlled workspace paths are never interpolated into ``cmd /c``.
A path segment named ``pp_jobs`` is not confinement.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.confinement import (
    COMFY_MACHINE_ID,
    XEON_MACHINE_ID,
    ConfinementError,
    reject_unsafe_string,
)
from project_pipeline.autonomy_runtime.service import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    SAFE_ENV_KEYS,
)
from project_pipeline.autonomy_runtime.windows_limits import NESTED_POOL_KEYS
from project_pipeline.autonomy_runtime.worker_allowlist import (
    remote_command_allowed,
    worker_launch_argv,
)

XEON_TAILNET_IPV4 = "100.107.207.66"
XEON_SSH_USER = "kines"
COMFY_TAILNET_IPV4 = "100.77.151.3"
COMFY_SSH_USER = "Windows 11"
DEFAULT_IDENTITY = Path.home() / ".ssh" / "id_ed25519"
SSH_CLIENT_ENV_KEYS = SAFE_ENV_KEYS | frozenset({"PROGRAMDATA"})
ALWAYS_DENIED_USERS = frozenset({"kevin"})
COMFY_DENIED_USERS = frozenset({"kevin", "kines"})
FLEET_SSH_TARGETS: Mapping[str, Mapping[str, str]] = {
    XEON_MACHINE_ID: {"host": XEON_TAILNET_IPV4, "user": XEON_SSH_USER},
    COMFY_MACHINE_ID: {"host": COMFY_TAILNET_IPV4, "user": COMFY_SSH_USER},
}
WORKER_ENTRYPOINT = ("python", "-m", "project_pipeline.autonomy_runtime.worker_entrypoint")
ACQUIRED_WORKSPACE_FILES = frozenset(
    {"junit.xml", "artifact_manifest.json", "useful_artifact.json"}
)


def parse_worker_stdout(stdout: str) -> dict[str, Any]:
    """Extract the worker JSON envelope from SSH stdout without executing it."""

    for line in reversed((stdout or "").splitlines()):
        text = line.strip()
        if not (text.startswith("{") and text.endswith("}")):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def job_stdout_metrics(stdout: str) -> dict[str, Any]:
    """Parse native-test metrics from job or worker JSON stdout."""

    metrics: dict[str, Any] = {}
    for candidate in (stdout,):
        parsed = parse_worker_stdout(str(candidate or ""))
        inner = parsed.get("stdout") if isinstance(parsed.get("stdout"), str) else None
        bodies = [parsed]
        if inner:
            nested = parse_worker_stdout(inner)
            if nested:
                bodies.append(nested)
        for body in bodies:
            for key in ("tests_run", "collected", "artifact_sha256", "junit_sha256"):
                if body.get(key) not in (None, "", 0, "0"):
                    metrics[key] = body.get(key)
            if body.get("context_consumption") is not None:
                metrics["context_consumption"] = body["context_consumption"]
    return metrics


def _is_running_started_record(payload: Mapping[str, Any]) -> bool:
    return payload.get("pid") is not None and payload.get("phase") == "RUNNING"


def _runner_accepts_input(runner: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(runner)
    except (TypeError, ValueError):
        return True
    if any(item.kind == inspect.Parameter.VAR_KEYWORD for item in signature.parameters.values()):
        return True
    return "input" in signature.parameters


def _bounded_popen_run(
    argv: list[str],
    *,
    env: dict[str, str],
    timeout_seconds: int,
    max_output_bytes: int,
    stdin_payload: str,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        shell=False,
    )
    overflow = {"stdout": False, "stderr": False}
    stdout_holder = {"text": ""}
    stderr_holder = {"text": ""}

    def _drain(stream: Any, key: str, holder: dict[str, str]) -> None:
        chunks: list[bytes] = []
        total = 0
        while True:
            data = stream.read(4096)
            if not data:
                break
            if total + len(data) > max_output_bytes:
                overflow[key] = True
                remain = max(0, max_output_bytes - total)
                if remain:
                    chunks.append(data[:remain])
                process.kill()
                break
            chunks.append(data)
            total += len(data)
        holder["text"] = b"".join(chunks).decode("utf-8", errors="replace")

    reader_out = threading.Thread(
        target=_drain, args=(process.stdout, "stdout", stdout_holder), daemon=True
    )
    reader_err = threading.Thread(
        target=_drain, args=(process.stderr, "stderr", stderr_holder), daemon=True
    )
    reader_out.start()
    reader_err.start()
    if process.stdin is not None:
        process.stdin.write(stdin_payload.encode("utf-8"))
        process.stdin.close()
    try:
        process.wait(timeout=timeout_seconds)
        timed_out = False
        exit_code = int(process.returncode or 0)
    except subprocess.TimeoutExpired:
        process.kill()
        timed_out = True
        exit_code = 124
    reader_out.join(timeout=5)
    reader_err.join(timeout=5)
    if overflow["stdout"] or overflow["stderr"]:
        exit_code = 125
        stderr_holder["text"] = (stderr_holder["text"] + "\n[truncated:output_limit]").strip()
    completed = subprocess.CompletedProcess(
        argv, exit_code, stdout_holder["text"], stderr_holder["text"]
    )
    completed.timed_out = timed_out  # type: ignore[attr-defined]
    completed.output_truncated = overflow["stdout"] or overflow["stderr"]  # type: ignore[attr-defined]
    return completed


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
    try:
        remote_worker = worker_launch_argv(machine_id)
    except ValueError:
        remote_worker = WORKER_ENTRYPOINT
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

    def acquire_workspace_file(
        self, working_directory: Path, name: str, dest: Path
    ) -> bytes | None:
        """Copy one job output file back and return its bytes. Does not trust stdout hashes."""

        if self.runner is not None or name not in ACQUIRED_WORKSPACE_FILES:
            return None
        try:
            reject_unsafe_string(str(working_directory), field="workspace")
        except ConfinementError:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        posix = f"{Path(working_directory).as_posix()}/{name}"
        completed = subprocess.run(
            [
                "scp",
                "-i",
                str(self.identity),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "BatchMode=yes",
                "-o",
                f"ConnectTimeout={self.connect_timeout}",
                "-o",
                f"User={self.user}",
                f"{self.host}:{posix}",
                str(dest),
            ],
            capture_output=True,
            check=False,
            shell=False,
            timeout=45,
            env=self._ssh_env(),
        )
        if completed.returncode != 0 or not dest.is_file():
            return None
        return dest.read_bytes()

    def _ssh_env(self) -> dict[str, str]:
        allowed = {item.upper() for item in SSH_CLIENT_ENV_KEYS}
        return {key: value for key, value in os.environ.items() if key.upper() in allowed}

    def _stdin_payload(
        self,
        *,
        command: list[str],
        working_directory: Path,
        extra: dict[str, str],
        action: str,
        target_pid: int | None,
        job_id: str | None = None,
        input_sha256: str | None = None,
        envelope: Mapping[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "action": action,
            "argv": command,
            "workspace": str(working_directory),
            "host_id": self.machine_id,
            "nested_env": extra,
            "job_id": job_id,
            "input_sha256": input_sha256,
        }
        if envelope:
            for key in (
                "lease_id",
                "fence",
                "source_sha",
                "source_tree",
                "profile_id",
                "principal",
                "overlay_sha256",
                "deadline_utc",
                "cpu_ceiling",
                "memory_mb_ceiling",
                "workspace_root",
                "output_contract_sha256",
                "context_pack",
                "pack_sha256",
                "require_context_consumption",
                "creation_time",
                "project_id",
            ):
                if key in envelope and envelope[key] is not None:
                    payload[key] = envelope[key]
        if target_pid is not None:
            payload["pid"] = int(target_pid)
        for key in ("creation_time", "principal", "job_id", "fence"):
            if envelope and envelope.get(key) is not None:
                payload[key] = envelope[key]
        return json.dumps(payload, sort_keys=True)

    def start_job(
        self,
        *,
        command: list[str],
        working_directory: Path,
        extra_env: dict[str, str] | None = None,
        envelope: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        input_sha256: str | None = None,
    ) -> subprocess.Popen[str]:
        extra = extra_env or {}
        if extra and any(key not in NESTED_POOL_KEYS for key in extra):
            raise ValueError("remote dispatch does not accept extra environment values")
        argv = build_ssh_argv(
            identity=self.identity,
            user=self.user,
            host=self.host,
            remote_argv=command,
            remote_cwd=str(working_directory),
            connect_timeout=self.connect_timeout,
        )
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._ssh_env(),
        )
        if process.stdin is None:
            process.kill()
            raise RuntimeError("ssh stdin is unavailable")
        process.stdin.write(
            self._stdin_payload(
                command=command,
                working_directory=working_directory,
                extra=extra,
                action="execute",
                target_pid=None,
                job_id=job_id,
                input_sha256=input_sha256,
                envelope=envelope,
            )
        )
        process.stdin.close()
        return process

    def read_started_record(
        self, process: subprocess.Popen[str], *, timeout_seconds: int = 30
    ) -> dict[str, Any]:
        if process.stdout is None:
            return {}
        deadline = time.time() + max(1, timeout_seconds)
        buf = ""
        while time.time() < deadline:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            buf += line
            parsed = parse_worker_stdout(buf)
            if _is_running_started_record(parsed):
                return parsed
            if parsed.get("ok") is False:
                return parsed
        return parse_worker_stdout(buf)

    def read_started_pid(
        self, process: subprocess.Popen[str], *, timeout_seconds: int = 12
    ) -> str | None:
        record = self.read_started_record(process, timeout_seconds=timeout_seconds)
        pid = record.get("pid")
        return str(pid) if pid is not None else None

    def kill_pid(
        self,
        pid: int,
        *,
        workspace: Path,
        job_id: str | None = None,
        fence: str | None = None,
        creation_time: str | None = None,
        principal: str | None = None,
        envelope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            command = list(worker_launch_argv(self.machine_id))
        except ValueError as error:
            raise ValueError("no remote worker script for kill") from error
        kill_envelope = dict(envelope or {})
        if job_id:
            kill_envelope["job_id"] = job_id
        if fence:
            kill_envelope["fence"] = fence
        if creation_time:
            kill_envelope["creation_time"] = creation_time
        if principal:
            kill_envelope["principal"] = principal
        return self.execute(
            command=command,
            working_directory=workspace,
            action="kill",
            target_pid=int(pid),
            timeout_seconds=20,
            job_id=job_id,
            envelope=kill_envelope or None,
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
        action: str = "execute",
        target_pid: int | None = None,
        job_id: str | None = None,
        input_sha256: str | None = None,
        envelope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        extra = extra_env or {}
        if extra and any(key not in NESTED_POOL_KEYS for key in extra):
            raise ValueError("remote dispatch does not accept extra environment values")
        _ = job_handle
        argv = build_ssh_argv(
            identity=self.identity,
            user=self.user,
            host=self.host,
            remote_argv=command,
            remote_cwd=str(working_directory),
            connect_timeout=self.connect_timeout,
        )
        env = self._ssh_env()
        stdin_payload = self._stdin_payload(
            command=command,
            working_directory=working_directory,
            extra=extra,
            action=action,
            target_pid=target_pid,
            job_id=job_id,
            input_sha256=input_sha256,
            envelope=envelope,
        )
        if self.runner is None:
            completed = _bounded_popen_run(
                argv,
                env=env,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                stdin_payload=stdin_payload,
            )
            raw_stdout = completed.stdout or ""
            raw_stderr = completed.stderr or ""
            timed_out = bool(getattr(completed, "timed_out", False))
            exit_code = completed.returncode
        else:
            kwargs: dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "check": False,
                "timeout": timeout_seconds,
                "env": env,
            }
            if _runner_accepts_input(self.runner):
                kwargs["input"] = stdin_payload
            try:
                completed = self.runner(argv, **kwargs)
            except TypeError as error:
                raise TypeError("ssh_runner_contract_error_after_dispatch") from error
            except subprocess.TimeoutExpired as error:
                raw_stdout = timeout_output_text(error.stdout or error.output)
                raw_stderr = timeout_output_text(error.stderr)
                timed_out = True
                exit_code = 124
            else:
                raw_stdout = completed.stdout or ""
                raw_stderr = completed.stderr or ""
                timed_out = False
                exit_code = completed.returncode
        stdout = raw_stdout[:max_output_bytes]
        stderr = raw_stderr[:max_output_bytes]
        worker = parse_worker_stdout(stdout)
        remote_pid = worker.get("pid")
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
            "remote_pid": None if remote_pid is None else str(remote_pid),
        }
        for key in ("ok", "killed"):
            if key in worker:
                payload[key] = worker[key]
        if worker.get("context_consumption") is not None:
            payload["context_consumption"] = worker["context_consumption"]
        job_metrics = job_stdout_metrics(str(worker.get("stdout") or stdout))
        payload.update(job_metrics)
        for key in ("reason", "phase"):
            value = worker.get(key)
            if value:
                payload[key] = value
        payload["payload_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return payload


def isolated_remote_worker_loss(
    adapter: SshDispatchAdapter,
    *,
    workspace: Path,
    hold_script: str,
) -> dict[str, Any]:
    """Kill the remote worker process; do not treat SSH-client timeout as that kill."""

    command = [
        "python",
        hold_script,
        "--job-id",
        "hold",
        "--seconds",
        "20",
        "--output",
        "hold.json",
    ]
    process = adapter.start_job(command=command, working_directory=workspace)
    remote_pid = adapter.read_started_pid(process)
    if not remote_pid:
        process.kill()
        return {
            "ok": False,
            "kind": "isolated_worker_process_loss",
            "reason": "pid_not_observed",
            "recovered": False,
            "ssh_client_termination": process.poll() is not None,
        }
    kill_payload = adapter.kill_pid(int(remote_pid), workspace=workspace)
    ssh_client_killed = False
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        ssh_client_killed = True
    worker = parse_worker_stdout(str(kill_payload.get("stdout") or ""))
    killed = bool(worker.get("killed") or worker.get("already_gone"))
    ok = bool(killed and not ssh_client_killed)
    return {
        "ok": ok,
        "kind": "isolated_worker_process_loss",
        "recovered": ok,
        "remote_pid": remote_pid,
        "killed": killed,
        "ssh_client_termination": ssh_client_killed,
        "timed_out": ssh_client_killed,
        "kill_exit_code": kill_payload.get("exit_code"),
        "ssh_exit_code": process.returncode,
        "reason": None if ok else "ssh_client_kill_or_remote_kill_unconfirmed",
    }
