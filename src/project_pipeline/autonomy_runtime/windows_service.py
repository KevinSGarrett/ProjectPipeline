from __future__ import annotations

import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVICE_NAME = "ProjectPipelineAutonomy"
DEFAULT_STOP_SECONDS = 15


def quote_windows(argument: str) -> str:
    if not argument:
        return '""'
    if any(ch in argument for ch in ' \t"'):
        escaped = argument.replace('"', r"\"")
        return f'"{escaped}"'
    return argument


def quote_command(parts: list[str]) -> str:
    return " ".join(quote_windows(part) for part in parts)


@dataclass(frozen=True)
class WindowsServicePaths:
    service_name: str
    executable: Path
    state_path: Path
    log_path: Path
    working_directory: Path
    pid_path: Path
    stop_flag_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "service_name": self.service_name,
            "executable": str(self.executable),
            "state_path": str(self.state_path),
            "log_path": str(self.log_path),
            "working_directory": str(self.working_directory),
            "pid_path": str(self.pid_path),
            "stop_flag_path": str(self.stop_flag_path),
        }


def build_paths(
    *,
    root: Path,
    state_path: Path | None = None,
    log_path: Path | None = None,
    executable: Path | None = None,
    service_name: str = SERVICE_NAME,
) -> WindowsServicePaths:
    root = root.resolve()
    state_dir = root / "state"
    return WindowsServicePaths(
        service_name=service_name,
        executable=(executable or Path(sys.executable)).resolve(),
        state_path=(state_path or (state_dir / "autonomy-supervisor.db")).resolve(),
        log_path=(log_path or (state_dir / "autonomy-service.log")).resolve(),
        working_directory=root,
        pid_path=(state_dir / "autonomy-service.pid").resolve(),
        stop_flag_path=(state_dir / "autonomy-service.stop").resolve(),
    )


def plan_service_commands(paths: WindowsServicePaths, script: Path) -> dict[str, str]:
    bin_path = quote_command(
        [
            str(paths.executable),
            str(script.resolve()),
            "--foreground",
            "--state",
            str(paths.state_path),
            "--log",
            str(paths.log_path),
            "--working-directory",
            str(paths.working_directory),
        ]
    )
    return {
        "install": quote_command(
            ["sc.exe", "create", paths.service_name, f"binPath={bin_path}", "start=demand"]
        ),
        "start": quote_command(["sc.exe", "start", paths.service_name]),
        "status": quote_command(["sc.exe", "query", paths.service_name]),
        "stop": quote_command(["sc.exe", "stop", paths.service_name]),
        "restart": quote_command(["sc.exe", "stop", paths.service_name])
        + " && "
        + quote_command(["sc.exe", "start", paths.service_name]),
        "uninstall": quote_command(["sc.exe", "delete", paths.service_name]),
    }


class AutonomyRuntimeWindowsService:
    """Foreground Windows-native control boundary with durable checkpoint and restart resume."""

    def __init__(self, paths: WindowsServicePaths) -> None:
        self.paths = paths
        self.paths.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._stopping = False

    def _write_log(self, message: str) -> None:
        self.paths.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.paths.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(UTC).isoformat()} {message}\n")

    def _checkpoint(self, payload: dict[str, Any]) -> None:
        checkpoint = self.paths.state_path.with_suffix(".checkpoint.json")
        checkpoint.write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    def health(self) -> dict[str, Any]:
        pid = None
        if self.paths.pid_path.exists():
            raw = self.paths.pid_path.read_text(encoding="utf-8").strip()
            pid = int(raw) if raw.isdigit() else None
        stale_pid = False
        if pid is not None:
            try:
                os.kill(pid, 0)
            except OSError:
                stale_pid = True
        return {
            "service_name": self.paths.service_name,
            "pid": pid,
            "stale_pid": stale_pid,
            "state_path": str(self.paths.state_path),
            "log_path": str(self.paths.log_path),
            "stop_requested": self.paths.stop_flag_path.exists(),
            "checkpoint_exists": self.paths.state_path.with_suffix(".checkpoint.json").exists(),
        }

    def request_stop(self) -> None:
        self.paths.stop_flag_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.stop_flag_path.write_text("stop\n", encoding="utf-8")
        self._stopping = True

    def run_foreground(self, *, max_seconds: float | None = None) -> int:
        if not self.paths.executable.exists():
            self._write_log("missing executable")
            return 2
        if self.paths.pid_path.exists():
            health = self.health()
            if health["stale_pid"]:
                self.paths.pid_path.unlink()
            elif health["pid"] not in {None, os.getpid()}:
                self._write_log("already running")
                return 3
        self.paths.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        if self.paths.stop_flag_path.exists():
            self.paths.stop_flag_path.unlink()
        started = time.monotonic()
        self._checkpoint(
            {
                "status": "RUNNING",
                "pid": os.getpid(),
                "started_at_utc": datetime.now(UTC).isoformat(),
            }
        )
        self._write_log("foreground start")

        def _handle(_signum: int, _frame: object) -> None:
            self.request_stop()

        signal.signal(signal.SIGINT, _handle)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handle)
        exit_code = 0
        try:
            while not self._stopping and not self.paths.stop_flag_path.exists():
                self._checkpoint(
                    {
                        "status": "RUNNING",
                        "pid": os.getpid(),
                        "heartbeat_at_utc": datetime.now(UTC).isoformat(),
                    }
                )
                if max_seconds is not None and (time.monotonic() - started) >= max_seconds:
                    break
                time.sleep(0.05)
        except Exception as error:
            self._write_log(f"crash {error}")
            exit_code = 1
        finally:
            self._checkpoint(
                {
                    "status": "STOPPED",
                    "pid": os.getpid(),
                    "stopped_at_utc": datetime.now(UTC).isoformat(),
                }
            )
            self._write_log("foreground stop")
            if self.paths.pid_path.exists():
                self.paths.pid_path.unlink()
            if self.paths.stop_flag_path.exists():
                self.paths.stop_flag_path.unlink()
        return exit_code
