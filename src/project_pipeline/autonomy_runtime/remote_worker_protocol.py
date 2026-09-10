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
from project_pipeline.autonomy_runtime.context_validation import (
    NATIVE_PASS,
    consume_pack_on_worker,
    job_input_digest,
    write_pack,
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
from project_pipeline.autonomy_runtime.worker_runtime_identity import (
    authority_identity,
    identity_matches,
    local_runtime_identity,
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
    "input_sha256",
)
MAX_OUTPUT_BYTES = 65536
WORKER_CLAIM_RUNNING = "RUNNING"
WORKER_CLAIM_COMPLETE = "COMPLETE"
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


def _print_running_record(child_pid: int, child_creation_time: str | None) -> None:
    worker_pid = os.getpid()
    print(
        json.dumps(
            {
                "ok": True,
                "pid": worker_pid,
                "creation_time": process_creation_filetime(worker_pid),
                "child_pid": child_pid,
                "child_creation_time": child_creation_time,
                "phase": "RUNNING",
            },
            sort_keys=True,
        ),
        flush=True,
    )


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


def _remaining_deadline_seconds(raw: object) -> int:
    if not raw:
        return 1
    try:
        deadline = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return max(1, int((deadline.astimezone(UTC) - datetime.now(UTC)).total_seconds()))
    except ValueError:
        return 1


def _zero_exit(value: object) -> bool:
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


def _load_cache(path: Path, identity: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = _read_json_object(path)
    if str(payload.get("authority_identity") or "") != identity:
        return None
    if str(payload.get("claim_state") or "") != WORKER_CLAIM_COMPLETE:
        return None
    if payload.get("ok") is not True or not _zero_exit(payload.get("exit_code")):
        return None
    payload["duplicate"] = True
    return payload


def _store_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _claim_worker_execution(cache: Path, identity: str, payload: dict[str, Any]) -> dict[str, Any]:
    cache.parent.mkdir(parents=True, exist_ok=True)
    cached = _load_cache(cache, identity)
    if cached is not None:
        return {"ok": True, "duplicate": True, "result": cached}
    claim = cache.with_suffix(".claim")
    record = {
        "claim_state": WORKER_CLAIM_RUNNING,
        "authority_identity": identity,
        "job_id": str(payload.get("job_id") or ""),
        "fence": str(payload.get("fence") or ""),
        "principal": str(payload.get("principal") or ""),
        "source_sha": str(payload.get("source_sha") or ""),
        "pid": os.getpid(),
        "started_at_utc": datetime.now(UTC).isoformat(),
    }
    try:
        fd = os.open(str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = _load_cache(cache, identity)
        if existing is not None:
            return {"ok": True, "duplicate": True, "result": existing}
        claimed = _read_json_object(claim)
        if str(claimed.get("authority_identity") or "") != identity:
            return {"ok": False, "reason": "incompatible_cache_identity"}
        return {"ok": False, "reason": "unresolved_in_flight"}
    try:
        os.write(fd, (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return {"ok": True, "duplicate": False, "claim": claim}


def _complete_worker_claim(cache: Path, claim: Path, result: dict[str, Any]) -> None:
    result = dict(result)
    result["claim_state"] = WORKER_CLAIM_COMPLETE
    _store_cache(cache, result)
    with suppress(OSError):
        claim.unlink()


def _release_worker_claim(claim: Path | None) -> None:
    if claim is None:
        return
    with suppress(OSError):
        claim.unlink()


def _spawn_enforced(
    *,
    argv: list[str],
    workspace: Path,
    env: dict[str, str],
    cpu_ceiling: int,
    memory_mb_ceiling: int,
    deadline_seconds: int,
    on_started: Callable[[int, str | None], None] | None = None,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    limits = enforce_or_reject(
        cpu_ceiling=cpu_ceiling,
        memory_mb_ceiling=memory_mb_ceiling,
        deadline_seconds=deadline_seconds,
    )
    handle = int(limits["handle"])
    started: dict[str, Any] = {}

    def _capture(child_pid: int, child_creation: str | None) -> None:
        started["pid"] = child_pid
        started["creation_time"] = child_creation
        _print_running_record(child_pid, child_creation)
        if on_started is not None:
            on_started(child_pid, child_creation)

    try:
        completed = assign_and_wait(
            command=argv,
            working_directory=workspace,
            timeout_seconds=deadline_seconds,
            env=env,
            handle=handle,
            on_started=_capture,
            max_output_bytes=max_output_bytes,
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
        "output_truncated": bool(getattr(completed, "output_truncated", False)),
    }


def run_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "execute")
    if action == "kill":
        return _kill(payload)
    if action == "measure":
        return _fail("use_controller_cim")
    host_id = str(payload.get("host_id") or "")
    if not host_id:
        return _fail("authority_missing", extra={"missing": ["host_id"]})
    if host_id not in APPROVED_WORKER_HOSTS:
        return _fail("wrong_host")
    missing = [key for key in REQUIRED_EXECUTE if not payload.get(key)]
    if missing:
        return _fail("authority_missing", extra={"missing": missing})
    live = local_runtime_identity(protocol_file=str(globals().get("__file__") or ""))
    identity_failures = identity_matches(payload, live, required_host=host_id)
    if identity_failures:
        return _fail("authority_unverified", extra={"failures": list(identity_failures)})
    argv_raw = payload.get("argv")
    if not isinstance(argv_raw, list) or not argv_raw:
        return _fail("argv_not_confined")
    argv = [str(item) for item in argv_raw]
    if not argv_is_confined(tuple(argv)):
        return _fail("argv_not_confined")
    if not remote_command_allowed(tuple(argv)):
        return _fail("argv_not_approved")
    workspace = str(payload.get("workspace") or "")
    workspace_root = str(payload.get("workspace_root") or "")
    job_id = str(payload.get("job_id") or "")
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
    if not input_sha256 or len(input_sha256) != 64:
        return _fail("input_digest_required")
    if action == "consume_context":
        pack_path = Path(workspace) / "context_pack.json"
        consumed = consume_pack_on_worker({**payload, "pack_path": str(pack_path)})
        if not consumed.get("ok"):
            return _fail(str(consumed.get("reason") or "pack_unconsumed"))
        return consumed
    require_pack = bool(
        payload.get("require_context_consumption")
        or payload.get("context_pack") is not None
        or payload.get("pack_sha256")
    )
    if require_pack:
        pack_digest = str(payload.get("pack_sha256") or "")
        if len(pack_digest) != 64:
            return _fail("pack_digest_required")
        expected_input = job_input_digest(
            task_id=job_id,
            source_sha=str(payload.get("source_sha") or ""),
            source_tree=str(payload.get("source_tree") or ""),
            overlay_sha256=str(payload.get("overlay_sha256") or ""),
            pack_sha256=pack_digest,
            selection=(NATIVE_PASS,),
        )
        if input_sha256 != expected_input:
            return _fail("input_digest_mismatch")
    identity = authority_identity(payload)
    claim = None
    if cache is not None:
        claimed = _claim_worker_execution(cache, identity, payload)
        if claimed.get("duplicate"):
            return claimed["result"]
        if not claimed.get("ok"):
            return _fail(str(claimed.get("reason") or "worker_claim_failed"))
        claim_path = claimed.get("claim")
        claim = claim_path if isinstance(claim_path, Path) else None
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

    try:
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
        if cpu < 1 or memory_mb < 1:
            return _fail("invalid_limits")
        Path(workspace).mkdir(parents=True, exist_ok=True)
        consumed: dict[str, Any] | None = None
        pack = payload.get("context_pack")
        if (
            pack is not None
            or payload.get("pack_sha256")
            or payload.get("require_context_consumption")
        ):
            pack_path = Path(workspace) / "context_pack.json"
            if isinstance(pack, dict):
                write_pack(Path(workspace), pack)
            consumed = consume_pack_on_worker({**payload, "pack_path": str(pack_path)})
            if not consumed.get("ok"):
                return _fail(str(consumed.get("reason") or "pack_unconsumed"))
        remaining = _remaining_deadline_seconds(payload.get("deadline_utc"))
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
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        truncated = bool(
            getattr(completed, "output_truncated", False) or enforced.get("output_truncated")
        )
        if truncated:
            stderr = (stderr + "\n[truncated:output_limit]").strip()
        worker_pid = os.getpid()
        result = {
            "ok": completed.returncode == 0 and not truncated,
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
            "source_sha": str(payload.get("source_sha") or ""),
            "source_tree": str(payload.get("source_tree") or ""),
            "overlay_sha256": str(payload.get("overlay_sha256") or ""),
            "limit_mechanism": mechanism,
            "duplicate": False,
            "truncated": truncated,
            "authority_identity": identity,
            "context_consumption": consumed,
        }
        if cache is not None and claim is not None:
            _complete_worker_claim(cache, claim, result)
            claim = None
        return result
    finally:
        _release_worker_claim(claim)


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
    if not job_id or not fence or not principal or not creation_time:
        return False
    if str(recorded.get("job_id") or "") != job_id:
        return False
    if str(recorded.get("fence") or "") != fence:
        return False
    if str(recorded.get("principal") or "") != principal:
        return False
    if str(pid_i) not in {
        str(recorded.get("pid") or ""),
        str(recorded.get("child_pid") or ""),
    }:
        return False
    recorded_times = {
        value
        for value in (
            str(recorded.get("creation_time") or ""),
            str(recorded.get("worker_creation_time") or ""),
        )
        if value
    }
    if creation_time not in recorded_times:
        return False
    live_creation = process_creation_filetime(pid_i)
    return bool(live_creation) and live_creation == creation_time


def _kill(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")
    fence = str(payload.get("fence") or "")
    principal = str(payload.get("principal") or "")
    creation_time = str(payload.get("creation_time") or "")
    try:
        pid_i = int(payload.get("pid") or 0)
    except (TypeError, ValueError):
        return _fail("invalid_pid")
    if (
        not job_id
        or not fence
        or not principal
        or not creation_time
        or not SAFE_JOB_ID.match(job_id)
    ):
        return _fail("ownership_identity_required", extra={"pid": pid_i})
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
        killed = completed.returncode == 0
        return {
            "ok": killed,
            "pid": pid_i,
            "killed": killed,
            "phase": "kill",
            "exit_code": completed.returncode,
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


def _managed_inbox(jobs_root: Path) -> Path:
    inbox = jobs_root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


def _intake_admitted_job(envelope_path: Path) -> dict[str, Any]:
    running = envelope_path.with_name(envelope_path.stem + ".running.json")
    try:
        envelope_path.replace(running)
    except OSError as error:
        return {"ok": False, "reason": "claim_failed", "detail": type(error).__name__}
    try:
        payload = json.loads(running.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": "invalid_envelope"}
    if not isinstance(payload, dict):
        return _fail("invalid_envelope")
    result = run_envelope(payload)
    result_path = running.with_name(str(payload.get("job_id") or "job") + ".result.json")
    result_path.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    with suppress(OSError):
        running.unlink()
    return result


def run_managed_worker(args: list[str]) -> int:
    """Stay resident, emit liveness, and own admitted inbox jobs until stop."""

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
    jobs_root = Path(_arg_value(args, "--jobs-root") or r"C:\ProgramData\ProjectPipeline\jobs")
    max_raw = _arg_value(args, "--max-seconds")
    try:
        max_seconds = float(max_raw) if max_raw else None
    except ValueError:
        return 2
    try:
        heartbeat.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
        inbox = _managed_inbox(jobs_root)
    except OSError:
        print(json.dumps(_fail("managed_state_unwritable"), sort_keys=True))
        return 2
    started = time.monotonic()
    digest = _script_digest()
    owned: list[str] = []
    try:
        while not stop_flag.is_file():
            for envelope_path in sorted(inbox.glob("*.envelope.json")):
                result = _intake_admitted_job(envelope_path)
                if result.get("job_id"):
                    owned.append(str(result["job_id"]))
            payload = {
                "ok": True,
                "phase": "managed",
                "pid": os.getpid(),
                "heartbeat_at_utc": datetime.now(UTC).isoformat(),
                "script_sha256": digest,
                "inbox": str(inbox),
                "owned_jobs": owned[-32:],
            }
            heartbeat.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            if max_seconds is not None and (time.monotonic() - started) >= max_seconds:
                break
            time.sleep(0.05)
    finally:
        if pid_file.is_file():
            with suppress(OSError):
                pid_file.unlink()
    print(
        json.dumps(
            {
                "ok": True,
                "phase": "managed_stop",
                "pid": os.getpid(),
                "owned_jobs": owned,
            },
            sort_keys=True,
        )
    )
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
    result = run_envelope(payload)
    print(json.dumps(result, sort_keys=True))
    return int(result.get("exit_code") or 0)
