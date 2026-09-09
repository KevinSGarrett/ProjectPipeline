"""Fixed remote worker entrypoint. Reads a JSON envelope from stdin."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.confinement import (
    ConfinementError,
    argv_is_confined,
    reject_unsafe_string,
)
from project_pipeline.autonomy_runtime.managed_worker import OWNED_TASK_NAMES, inspect_scheduled_task_xml
from project_pipeline.autonomy_runtime.providers import contains_secret_shaped
from project_pipeline.scheduler.host_observation import measure_local_inventory


def _cache_path(workspace: str, job_id: str) -> Path:
    return Path(workspace) / ".pp_worker_results" / f"{job_id}.json"


def _load_cached(workspace: str, job_id: str, input_sha256: str) -> dict[str, Any] | None:
    path = _cache_path(workspace, job_id)
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


def _store_cached(workspace: str, job_id: str, payload: dict[str, Any]) -> None:
    path = _cache_path(workspace, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def run_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "execute")
    if action == "measure":
        measured = measure_local_inventory()
        measured["pid"] = os.getpid()
        return measured
    if action == "inspect_task":
        task_name = str(payload.get("task_name") or "")
        if task_name not in OWNED_TASK_NAMES:
            return {"ok": False, "reason": "unowned_scheduled_task", "exit_code": 2}
        completed = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/XML"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        xml_text = completed.stdout or ""
        inspected = inspect_scheduled_task_xml(xml_text) if xml_text.strip() else {
            "ok": False,
            "reason": "task_xml_missing",
        }
        inspected["exit_code"] = completed.returncode
        inspected["ok"] = completed.returncode == 0 and xml_text.strip() != ""
        inspected["pid"] = os.getpid()
        return inspected
    argv = payload.get("argv")
    workspace = str(payload.get("workspace") or "")
    job_id = str(payload.get("job_id") or "")
    input_sha256 = str(payload.get("input_sha256") or "")
    if contains_secret_shaped(argv) or contains_secret_shaped(workspace):
        return {"ok": False, "reason": "secret_in_envelope", "exit_code": 2}
    if not isinstance(argv, list) or not argv_is_confined(tuple(str(item) for item in argv)):
        return {"ok": False, "reason": "argv_not_confined", "exit_code": 2}
    try:
        reject_unsafe_string(workspace, field="workspace")
    except ConfinementError as error:
        return {"ok": False, "reason": str(error), "exit_code": 2}
    if job_id and input_sha256:
        cached = _load_cached(workspace, job_id, input_sha256)
        if cached is not None:
            return cached
    nested = payload.get("nested_env") if isinstance(payload.get("nested_env"), dict) else {}
    env = os.environ.copy()
    for key, value in nested.items():
        env[str(key)] = str(value)
    completed = subprocess.run(
        [str(item) for item in argv],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        env=env,
    )
    stdout = (completed.stdout or "")[:65536]
    stderr = (completed.stderr or "")[:65536]
    result = {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "pid": os.getpid(),
        "output_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "job_id": job_id,
        "input_sha256": input_sha256,
        "duplicate": False,
    }
    if job_id and input_sha256 and completed.returncode == 0:
        _store_cached(workspace, job_id, result)
    return result


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "reason": "invalid_envelope", "exit_code": 2}))
        return 2
    result = run_envelope(payload if isinstance(payload, dict) else {})
    print(json.dumps(result, sort_keys=True))
    return int(result.get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
