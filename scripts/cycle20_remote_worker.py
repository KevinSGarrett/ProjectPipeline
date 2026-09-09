"""Standalone Cycle 20 remote worker. Standard library only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

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
    argv = payload.get("argv")
    workspace = str(payload.get("workspace") or "")
    if not isinstance(argv, list) or not argv or any(UNSAFE.search(str(item) or "") for item in argv):
        print(json.dumps({"ok": False, "reason": "argv_not_confined", "exit_code": 2}))
        return 2
    if not workspace or UNSAFE.search(workspace) or ".." in workspace:
        print(json.dumps({"ok": False, "reason": "workspace_unsafe", "exit_code": 2}))
        return 2
    nested = payload.get("nested_env") if isinstance(payload.get("nested_env"), dict) else {}
    env = os.environ.copy()
    for key, value in nested.items():
        env[str(key)] = str(value)
    Path(workspace).mkdir(parents=True, exist_ok=True)
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
