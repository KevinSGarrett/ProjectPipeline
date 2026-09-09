"""Standalone Cycle 20 remote worker. Standard library only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

UNSAFE = re.compile(r'[<>|&^%\n\r\x00"`]')


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "reason": "invalid_envelope", "exit_code": 2}))
        return 2
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "reason": "invalid_envelope", "exit_code": 2}))
        return 2
    action = str(payload.get("action") or "execute")
    if action == "measure":
        print(json.dumps({"ok": False, "reason": "use_controller_cim", "exit_code": 2}))
        return 2
    if action == "kill":
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            print(json.dumps({"ok": False, "reason": "invalid_pid", "exit_code": 2}))
            return 2
        if pid <= 4 or pid == os.getpid():
            print(
                json.dumps({"ok": False, "reason": "pid_not_killable", "pid": pid, "exit_code": 2})
            )
            return 2
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            )
            gone = completed.returncode == 0 or "not found" in (completed.stderr or "").lower()
            print(
                json.dumps(
                    {
                        "ok": True,
                        "pid": pid,
                        "killed": completed.returncode == 0,
                        "already_gone": gone and completed.returncode != 0,
                        "phase": "kill",
                        "exit_code": 0,
                    },
                    sort_keys=True,
                )
            )
            return 0
        try:
            os.kill(pid, 9)
            print(
                json.dumps(
                    {"ok": True, "pid": pid, "killed": True, "phase": "kill", "exit_code": 0}
                )
            )
            return 0
        except OSError:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "pid": pid,
                        "killed": False,
                        "already_gone": True,
                        "phase": "kill",
                        "exit_code": 0,
                    }
                )
            )
            return 0
    argv = payload.get("argv")
    workspace = str(payload.get("workspace") or "")
    if (
        not isinstance(argv, list)
        or not argv
        or any(UNSAFE.search(str(item) or "") for item in argv)
    ):
        print(json.dumps({"ok": False, "reason": "argv_not_confined", "exit_code": 2}))
        return 2
    if not workspace or UNSAFE.search(workspace) or ".." in workspace:
        print(json.dumps({"ok": False, "reason": "workspace_unsafe", "exit_code": 2}))
        return 2
    nested = payload.get("nested_env") if isinstance(payload.get("nested_env"), dict) else {}
    env = os.environ.copy()
    allowed_nested = {
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    }
    for key, value in nested.items():
        if str(key) in allowed_nested:
            env[str(key)] = str(value)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    print(
        json.dumps({"ok": True, "pid": os.getpid(), "phase": "started"}, sort_keys=True), flush=True
    )
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
    result = {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": (completed.stderr or "")[:65536],
        "pid": os.getpid(),
        "output_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
    }
    print(json.dumps(result, sort_keys=True))
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
