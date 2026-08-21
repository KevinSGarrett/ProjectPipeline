from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "start_autonomy_qualification_hidden.ps1"


def test_hidden_launcher_declares_required_windows_contract():
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "Start-Process" in text
    assert "-WindowStyle Hidden" in text
    assert "-ArgumentList" in text
    assert "-WorkingDirectory" in text
    assert "RedirectStandardOutput" in text
    assert "RedirectStandardError" in text
    assert "simulated_elapsed = $false" in text
    assert "UNATTENDED_4_HOUR" in text
    assert "UNATTENDED_24_HOUR" in text


def test_hidden_launcher_dry_run_emits_explicit_argument_array(tmp_path: Path):
    if os.name != "nt":
        return
    database = tmp_path / "ns" / "qualify.sqlite3"
    state = tmp_path / "ns" / "state"
    logs = tmp_path / "ns" / "logs"
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(LAUNCHER),
            "-RepositoryRoot",
            str(ROOT),
            "-PythonExe",
            sys.executable,
            "-Database",
            str(database),
            "-StatePath",
            str(state),
            "-LogDirectory",
            str(logs),
            "-Stage",
            "RECOVERY",
            "-HeartbeatSeconds",
            "0.05",
            "-Cycles",
            "1",
            "-DryRun",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    payload = json.loads(completed.stdout)
    assert payload["window_style"] == "Hidden"
    assert payload["working_directory"] == str(ROOT)
    assert payload["simulated_elapsed"] is False
    assert payload["argument_list"][1] == "run"
    assert "--stage" in payload["argument_list"]
    assert "RECOVERY" in payload["argument_list"]


def test_hidden_launcher_starts_bounded_recovery_and_writes_pid(tmp_path: Path):
    if os.name != "nt":
        return
    database = tmp_path / "ns" / "qualify.sqlite3"
    state = tmp_path / "ns" / "state"
    logs = tmp_path / "ns" / "logs"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(LAUNCHER),
            "-RepositoryRoot",
            str(ROOT),
            "-PythonExe",
            sys.executable,
            "-Database",
            str(database),
            "-StatePath",
            str(state),
            "-LogDirectory",
            str(logs),
            "-Stage",
            "RECOVERY",
            "-HeartbeatSeconds",
            "0.05",
            "-Cycles",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    payload = json.loads(completed.stdout)
    assert int(payload["pid"]) > 0
    assert Path(payload["pid_file"]).is_file()
    assert Path(payload["pid_file"]).read_text(encoding="utf-8").strip() == str(payload["pid"])
