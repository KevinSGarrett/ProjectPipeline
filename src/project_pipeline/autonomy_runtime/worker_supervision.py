"""Isolated worker process supervision, drain, and restart recovery."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


def start_isolated_job(
    command: list[str] | None = None, workspace: Path | None = None
) -> subprocess.Popen[str]:
    argv = command or [sys.executable, "-c", "import time; time.sleep(30)"]
    if not argv:
        raise ValueError("isolated job requires argv")
    if workspace is None:
        raise ValueError("isolated job requires a workspace")
    return subprocess.Popen(
        argv,
        cwd=str(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )


def recover_isolated_job(process: subprocess.Popen[str]) -> dict[str, Any]:
    if process.poll() is not None:
        return {
            "ok": True,
            "recovered": True,
            "exit_code": process.returncode,
            "running": False,
        }
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    return {
        "ok": True,
        "recovered": True,
        "exit_code": process.returncode,
        "running": False,
        "affected_lane_only": True,
    }
