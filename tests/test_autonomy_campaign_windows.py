from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "start_autonomy_campaign_hidden.ps1"
RECOVERY = ROOT / "scripts" / "register_autonomy_campaign_recovery.ps1"


def test_hidden_campaign_launcher_declares_windows_contract():
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "Start-Process" in text
    assert "-WindowStyle Hidden" in text
    assert "-ArgumentList" in text
    assert "-WorkingDirectory" in text
    assert "RedirectStandardOutput" in text
    assert "simulated_elapsed = $false" in text
    assert "run_autonomy_campaign.py" in text


def test_hidden_campaign_launcher_dry_run(tmp_path: Path):
    if os.name != "nt":
        return
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(LAUNCHER),
            "-RepositoryRoot",
            str(ROOT),
            "-PythonExe",
            __import__("sys").executable,
            "-Database",
            str(tmp_path / "campaign.sqlite3"),
            "-StatePath",
            str(tmp_path / "state"),
            "-LogDirectory",
            str(tmp_path / "logs"),
            "-EvidencePath",
            str(tmp_path / "evidence"),
            "-Pp384Evidence",
            str(tmp_path / "pp384.json"),
            "-DryRun",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    payload = json.loads(completed.stdout)
    assert payload["window_style"] == "Hidden"
    assert payload["simulated_elapsed"] is False
    assert payload["argument_list"][1] == "start"


def test_recovery_task_plan_is_hidden_and_non_interactive(tmp_path: Path):
    text = RECOVERY.read_text(encoding="utf-8")
    assert "Register-ScheduledTask" in text
    assert "Hidden" in text
    assert "simulated_elapsed = $false" in text
    if os.name != "nt":
        return
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(RECOVERY),
            "-Action",
            "plan",
            "-RepositoryRoot",
            str(ROOT),
            "-PythonExe",
            __import__("sys").executable,
            "-Database",
            str(tmp_path / "campaign.sqlite3"),
            "-LogDirectory",
            str(tmp_path / "logs"),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    payload = json.loads(completed.stdout)
    assert payload["window_style"] == "Hidden"
    assert payload["task_name"] == "ProjectPipelineAutonomyCampaign"
