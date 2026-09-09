"""Disable the two owned SYSTEM index tasks and register least-privilege replacements."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_pipeline.autonomy_runtime.managed_worker import (
    OWNED_TASK_NAMES,
    owned_task_retirement_plan,
)
from project_pipeline.autonomy_runtime.ssh_dispatch import FLEET_SSH_TARGETS
from project_pipeline.autonomy_runtime.worker_allowlist import HOST_PYTHON_EXECUTABLES

IDENTITY = Path.home() / ".ssh" / "id_ed25519"
HOST_TASKS = {
    "WIN-EVSH1DN8H5O": "ProjectPipelineFleetWorkerXeon",
    "COMFY-V4-CPU-01": "ProjectPipelineFleetWorkerComfy",
}


def _ssh(user: str, host: str, remote: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "ssh",
            "-i",
            str(IDENTITY),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-l",
            user,
            host,
            remote,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def main() -> int:
    results = []
    for machine_id, task_name in HOST_TASKS.items():
        if task_name not in OWNED_TASK_NAMES:
            continue
        target = FLEET_SSH_TARGETS[machine_id]
        python_exe = HOST_PYTHON_EXECUTABLES.get(machine_id)
        plan = owned_task_retirement_plan(task_name, python_executable=python_exe)
        if not plan.get("ok"):
            results.append(
                {
                    "machine_id": machine_id,
                    "task_name": task_name,
                    "ok": False,
                    "reason": plan.get("reason"),
                }
            )
            continue
        replacement = str(plan["replacement_name"])
        disable = _ssh(target["user"], target["host"], f"schtasks /Change /TN {task_name} /DISABLE")
        create_remote = " ".join(str(item) for item in plan["replacement_create_argv"])
        create = _ssh(target["user"], target["host"], create_remote)
        query = _ssh(
            target["user"], target["host"], f"schtasks /Query /TN {replacement} /V /FO LIST"
        )
        results.append(
            {
                "machine_id": machine_id,
                "task_name": task_name,
                "replacement": replacement,
                "disable_code": disable.returncode,
                "create_code": create.returncode,
                "query_code": query.returncode,
                "query_has_system": "SYSTEM" in (query.stdout or "").upper(),
                "rollback": list(plan["rollback_argv"]),
            }
        )
    print(json.dumps({"ok": True, "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
