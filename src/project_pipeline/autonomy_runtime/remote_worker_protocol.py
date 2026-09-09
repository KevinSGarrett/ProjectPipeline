"""Authoritative remote/managed worker protocol for Cycle 20.

SSH transport and scheduled managed workers share this entry point. Nested
thread-pool environment variables are never treated as memory, CPU, process, or
deadline enforcement.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.confinement import (
    ConfinementError,
    argv_is_confined,
    confine_remote_workspace,
)
from project_pipeline.autonomy_runtime.windows_limits import (
    NESTED_POOL_KEYS,
    ResourceLimitError,
    assign_and_wait,
    close_job_handle,
    enforce_or_reject,
    nested_pool_env,
    process_creation_filetime,
)
from project_pipeline.autonomy_runtime.worker_allowlist import (
    APPROVED_WORKER_HOSTS,
    PYTHON_NAMES,
    remote_command_allowed,
)

REQUIRED_EXECUTE = (
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
    "host_id",
    "workspace",
    "argv",
    "job_id",
)
SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _deployed_src() -> str | None:
    raw = globals().get("__file__")
    if not raw:
        return os.environ.get("PP_WORKER_SRC", "").strip() or None
    here = Path(str(raw)).resolve()
    try:
        src = here.parents[2]
    except IndexError:
        src = here.parent
    marker = src / "project_pipeline" / "autonomy_runtime" / "remote_worker_protocol.py"
    if marker.is_file():
        return str(src)
    extra = os.environ.get("PP_WORKER_SRC", "").strip()
    return extra or None


def _bound_job_env(env: dict[str, str]) -> dict[str, str]:
    src = _deployed_src()
    if src:
        env["PP_WORKER_SRC"] = src
        env["PYTHONPATH"] = src
    return env


def _resolve_job_python(argv: list[str]) -> list[str]:
    if argv and Path(argv[0]).name.lower() in PYTHON_NAMES:
        return [sys.executable, *argv[1:]]
    return argv


def _fail(reason: str, *, extra: dict[str, object] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "reason": reason, "exit_code": 2}
    if extra:
        payload.update(extra)
    return payload


def _safe_result_path(workspace: str, job_id: str, suffix: str) -> Path | None:
    if not SAFE_JOB_ID.match(job_id):
        return None
    root = Path(workspace) / ".pp_worker_results"
    path = root / f"{job_id}{suffix}"
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return path


def _safe_cache(workspace: str, job_id: str) -> Path | None:
    return _safe_result_path(workspace, job_id, ".json")


def _safe_own(workspace: str, job_id: str) -> Path | None:
    return _safe_result_path(workspace, job_id, ".own.json")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _record_running_ownership(payload: dict[str, Any]) -> Path | None:
    workspace = str(payload.get("workspace") or "")
    job_id = str(payload.get("job_id") or "")
    own = _safe_own(workspace, job_id) if workspace and job_id else None
    if own is None:
        return None
    _store_cache(
        own,
        {
            "job_id": job_id,
            "fence": str(payload.get("fence") or ""),
            "principal": str(payload.get("principal") or ""),
            "pid": os.getpid(),
            "child_pid": 0,
            "phase": "RUNNING",
            "input_sha256": str(payload.get("input_sha256") or ""),
            "worker_creation_time": process_creation_filetime(os.getpid()),
        },
    )
    return own


def _deadline_passed(raw: object) -> bool:
    text = str(raw or "")
    try:
        deadline = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return True
    return datetime.now(UTC) > deadline


def _load_cache(path: Path, input_sha256: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if str(payload.get("input_sha256") or "") != input_sha256:
        return None
    payload["duplicate"] = True
    return payload


def _store_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _spawn_enforced(
    *,
    argv: list[str],
    workspace: Path,
    env: dict[str, str],
    cpu_ceiling: int,
    memory_mb_ceiling: int,
    deadline_seconds: int,
    on_started: Callable[[int, str | None], None] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    limits = enforce_or_reject(
        cpu_ceiling=cpu_ceiling,
        memory_mb_ceiling=memory_mb_ceiling,
        deadline_seconds=deadline_seconds,
    )
    handle = int(limits["handle"])
    started: dict[str, Any] = {}

    def _capture(pid: int, creation: str | None) -> None:
        started["pid"] = pid
        started["creation_time"] = creation
        print(
            json.dumps(
                {
                    "ok": True,
                    "pid": os.getpid(),
                    "child_pid": pid,
                    "creation_time": creation,
                    "phase": "RUNNING",
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if on_started is not None:
            on_started(pid, creation)

    try:
        completed = assign_and_wait(
            command=argv,
            working_directory=workspace,
            timeout_seconds=deadline_seconds,
            env=env,
            handle=handle,
            on_started=_capture,
        )
    finally:
        close_job_handle(handle)
    pid = int(started.get("pid") or getattr(completed, "pid", 0) or 0)
    creation = started.get("creation_time")
    if creation is None:
        creation = getattr(completed, "creation_time", None)
    return completed, {
        "mechanism": limits.get("mechanism"),
        "cpu_rate": limits.get("cpu_rate"),
        "pid": pid,
        "creation_time": creation,
    }


def run_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "execute")
    if action == "kill":
        return _kill(payload)
    if action == "measure":
        return _fail("use_controller_cim")
    host_id = str(payload.get("host_id") or "")
    if host_id and host_id not in APPROVED_WORKER_HOSTS:
        return _fail("wrong_host")
    production = host_id in APPROVED_WORKER_HOSTS
    missing = [key for key in REQUIRED_EXECUTE if not payload.get(key)]
    if production and missing:
        return _fail("authority_missing", extra={"missing": missing})
    argv_raw = payload.get("argv")
    if not isinstance(argv_raw, list) or not argv_raw:
        return _fail("argv_not_confined")
    argv = [str(item) for item in argv_raw]
    if not argv_is_confined(tuple(argv)):
        return _fail("argv_not_confined")
    if production and not remote_command_allowed(tuple(argv)):
        return _fail("argv_not_approved")
    workspace = str(payload.get("workspace") or "")
    workspace_root = str(payload.get("workspace_root") or "")
    job_id = str(payload.get("job_id") or "")
    if production:
        if host_id not in APPROVED_WORKER_HOSTS:
            return _fail("wrong_host")
        try:
            confine_remote_workspace(workspace, allowed_root=workspace_root)
        except ConfinementError as error:
            return _fail(str(error))
        if _deadline_passed(payload.get("deadline_utc")):
            return _fail("expired_deadline")
    cache = _safe_cache(workspace, job_id) if job_id else None
    if job_id and cache is None:
        return _fail("job_id_unsafe")
    input_sha256 = str(payload.get("input_sha256") or "")
    if cache is not None and input_sha256:
        cached = _load_cache(cache, input_sha256)
        if cached is not None:
            return cached
    own = _record_running_ownership(payload)

    def _child_started(pid: int, creation: str | None) -> None:
        if own is None:
            return
        recorded = _read_json_object(own)
        recorded.update(
            {
                "child_pid": pid,
                "creation_time": creation,
                "phase": "RUNNING",
            }
        )
        _store_cache(own, recorded)

    nested = payload.get("nested_env") if isinstance(payload.get("nested_env"), dict) else {}
    env = os.environ.copy()
    for key, value in nested.items():
        if str(key) in NESTED_POOL_KEYS:
            env[str(key)] = str(value)
    env = _bound_job_env(env)
    argv = _resolve_job_python(argv)
    try:
        cpu = int(payload.get("cpu_ceiling") or 0)
        memory_mb = int(payload.get("memory_mb_ceiling") or 0)
    except (TypeError, ValueError):
        return _fail("invalid_limits")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    if production or (cpu >= 1 and memory_mb >= 1):
        remaining = 1
        raw_deadline = payload.get("deadline_utc")
        if raw_deadline:
            try:
                deadline = datetime.fromisoformat(str(raw_deadline).replace("Z", "+00:00"))
                remaining = max(
                    1, int((deadline.astimezone(UTC) - datetime.now(UTC)).total_seconds())
                )
            except ValueError:
                remaining = 1
        env.update(nested_pool_env(max(1, cpu)))
        try:
            completed, enforced = _spawn_enforced(
                argv=argv,
                workspace=Path(workspace),
                env=env,
                cpu_ceiling=max(1, cpu),
                memory_mb_ceiling=max(1, memory_mb),
                deadline_seconds=remaining,
                on_started=_child_started,
            )
        except ResourceLimitError as error:
            return _fail(str(error))
        except subprocess.TimeoutExpired:
            return _fail("deadline_enforced", extra={"timed_out": True})
        child_pid = int(enforced.get("pid") or 0)
        creation_time = enforced.get("creation_time")
        mechanism = enforced.get("mechanism")
    else:
        completed = subprocess.run(
            argv,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            env=env,
        )
        child_pid = os.getpid()
        creation_time = None
        mechanism = "unbounded_local_fixture"
    stdout = (completed.stdout or "")[:65536]
    stderr = (completed.stderr or "")[:65536]
    worker_pid = os.getpid()
    result = {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "pid": worker_pid,
        "child_pid": child_pid,
        "creation_time": creation_time,
        "output_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "job_id": job_id,
        "input_sha256": input_sha256,
        "fence": str(payload.get("fence") or ""),
        "principal": str(payload.get("principal") or ""),
        "limit_mechanism": mechanism,
        "duplicate": False,
    }
    if cache is not None and input_sha256 and completed.returncode == 0:
        _store_cache(cache, result)
    return result


def _ownership_records(workspace: str, job_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in (
        _safe_own(workspace, job_id) if workspace else None,
        _safe_cache(workspace, job_id) if workspace else None,
    ):
        if path is not None and path.is_file():
            loaded = _read_json_object(path)
            if loaded:
                records.append(loaded)
    return records


def _pid_is_owned(
    recorded: dict[str, Any],
    *,
    job_id: str,
    fence: str,
    principal: str,
    pid_i: int,
    creation_time: str,
) -> bool:
    if str(recorded.get("job_id") or "") != job_id:
        return False
    if str(recorded.get("fence") or "") != fence:
        return False
    if str(pid_i) not in {
        str(recorded.get("pid") or ""),
        str(recorded.get("child_pid") or ""),
    }:
        return False
    if principal and str(recorded.get("principal") or "") not in {"", principal}:
        return False
    recorded_times = {
        value
        for value in (
            str(recorded.get("creation_time") or ""),
            str(recorded.get("worker_creation_time") or ""),
        )
        if value
    }
    if creation_time and recorded_times and creation_time not in recorded_times:
        return False
    live_creation = process_creation_filetime(pid_i)
    return not (live_creation and creation_time and live_creation != creation_time)


def _kill(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")
    fence = str(payload.get("fence") or "")
    principal = str(payload.get("principal") or "")
    creation_time = str(payload.get("creation_time") or "")
    try:
        pid_i = int(payload.get("pid") or 0)
    except (TypeError, ValueError):
        return _fail("invalid_pid")
    if not job_id or not fence or not SAFE_JOB_ID.match(job_id):
        return _fail("unowned_pid", extra={"pid": pid_i})
    if pid_i <= 4 or pid_i == os.getpid():
        return _fail("pid_not_killable", extra={"pid": pid_i})
    workspace = str(payload.get("workspace") or "")
    owned = any(
        _pid_is_owned(
            recorded,
            job_id=job_id,
            fence=fence,
            principal=principal,
            pid_i=pid_i,
            creation_time=creation_time,
        )
        for recorded in _ownership_records(workspace, job_id)
    )
    if not owned:
        return _fail("unowned_pid", extra={"pid": pid_i})
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid_i), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        return {
            "ok": True,
            "pid": pid_i,
            "killed": completed.returncode == 0,
            "phase": "kill",
            "exit_code": 0,
            "job_id": job_id,
            "fence": fence,
        }
    return _fail("kill_unsupported")


def _arg_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    index = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _script_digest() -> str:
    raw = globals().get("__file__")
    if not raw:
        return ""
    path = Path(str(raw))
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def run_managed_worker(args: list[str]) -> int:
    """Stay resident, emit liveness, and stop only on the owned stop flag."""

    heartbeat = Path(
        _arg_value(args, "--heartbeat")
        or r"C:\ProgramData\ProjectPipeline\jobs\managed_heartbeat.json"
    )
    stop_flag = Path(
        _arg_value(args, "--stop-flag") or r"C:\ProgramData\ProjectPipeline\jobs\managed.stop"
    )
    pid_file = Path(
        _arg_value(args, "--pid-file") or r"C:\ProgramData\ProjectPipeline\jobs\managed.pid"
    )
    max_raw = _arg_value(args, "--max-seconds")
    try:
        max_seconds = float(max_raw) if max_raw else None
    except ValueError:
        return 2
    try:
        heartbeat.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        print(json.dumps(_fail("managed_state_unwritable"), sort_keys=True))
        return 2
    started = time.monotonic()
    digest = _script_digest()
    try:
        while not stop_flag.is_file():
            payload = {
                "ok": True,
                "phase": "managed",
                "pid": os.getpid(),
                "heartbeat_at_utc": datetime.now(UTC).isoformat(),
                "script_sha256": digest,
            }
            heartbeat.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            if max_seconds is not None and (time.monotonic() - started) >= max_seconds:
                break
            time.sleep(0.05)
    finally:
        if pid_file.is_file():
            with suppress(OSError):
                pid_file.unlink()
    print(json.dumps({"ok": True, "phase": "managed_stop", "pid": os.getpid()}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--managed" in args:
        return run_managed_worker(args)
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        result = _fail("invalid_envelope")
        print(json.dumps(result, sort_keys=True))
        return 2
    if not isinstance(payload, dict):
        result = _fail("invalid_envelope")
        print(json.dumps(result, sort_keys=True))
        return 2
    if str(payload.get("action") or "execute") == "execute":
        _record_running_ownership(payload)
        print(
            json.dumps(
                {
                    "ok": True,
                    "pid": os.getpid(),
                    "phase": "started",
                    "creation_time": process_creation_filetime(os.getpid()),
                    "job_id": payload.get("job_id"),
                    "fence": payload.get("fence"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    result = run_envelope(payload)
    print(json.dumps(result, sort_keys=True))
    return int(result.get("exit_code") or 0)
