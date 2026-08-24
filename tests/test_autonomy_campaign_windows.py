from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.campaign import (
    REQUIRED_PP384_STAGES,
    CampaignController,
    inspect_worktree_identity,
    observe_windows_scheduled_task,
)

ROOT = Path(__file__).resolve().parents[1]


def _identity() -> dict:
    return {"sha": "a" * 40, "tree": "b" * 40, "dirty": False, "ok": True}


def _live_identity() -> dict:
    identity = inspect_worktree_identity(ROOT)
    if not identity.get("ok") or identity.get("dirty"):
        pytest.skip("disposable recovery task requires a clean worktree identity")
    return identity


def _pp384_evidence(path: Path) -> Path:
    stages = [
        {"stage_id": stage_id, "outcome": "PASSED", "reasons": [], "observations": {}}
        for stage_id in REQUIRED_PP384_STAGES
    ]
    path.write_text(
        json.dumps({"schema_version": "1.0.0", "task_id": "PP-TASK-000384", "stages": stages}),
        encoding="utf-8",
    )
    return path


LAUNCHER = ROOT / "scripts" / "start_autonomy_campaign_hidden.ps1"
RECOVERY = ROOT / "scripts" / "register_autonomy_campaign_recovery.ps1"
PROBE = ROOT / "scripts" / "autonomy_campaign_recovery_probe.py"
LIVE_TASK = "ProjectPipelineAutonomyCampaign"


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
    assert "MaxValue" not in RECOVERY.read_text(encoding="utf-8")
    assert "autonomy_campaign_recovery_probe.py" in RECOVERY.read_text(encoding="utf-8")


def test_recovery_probe_bootstraps_imports_without_pythonpath(tmp_path: Path):
    config_path = tmp_path / "recovery_probe.json"
    status_path = tmp_path / "status.json"
    payload = {
        "repository_root": str(ROOT),
        "python_exe": sys.executable,
        "database": str(tmp_path / "campaign.sqlite3"),
        "campaign_id": "",
        "status_path": str(status_path),
        "pid_path": str(tmp_path / "campaign.pid"),
        "log_directory": str(tmp_path),
        "heartbeat_seconds": 0.2,
        "heartbeat_max_age_seconds": 1.0,
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        # A different checkout is deliberately inherited: the probe must still
        # load modules from its bound candidate checkout.
        "PYTHONPATH": str(Path("C:/Project_X/src")),
    }
    result = subprocess.run(
        [sys.executable, str(PROBE), "--config", str(config_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(status_path.read_text(encoding="utf-8"))
    assert written["action"] == "no-campaign"
    assert Path(written["campaign_module"]).resolve().is_relative_to(ROOT / "src")
    assert written["user_action_required"] is False


def _register(
    action: str,
    tmp_path: Path,
    task_name: str,
    campaign_id: str = "",
    *,
    expected_sha: str = "a" * 40,
    expected_tree: str = "b" * 40,
) -> dict:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(RECOVERY),
            "-Action",
            action,
            "-RepositoryRoot",
            str(ROOT),
            "-PythonExe",
            sys.executable,
            "-Database",
            str(tmp_path / "campaign.sqlite3"),
            "-LogDirectory",
            str(tmp_path / "logs"),
            "-TaskName",
            task_name,
            "-CampaignId",
            campaign_id,
            "-ExpectedSha",
            expected_sha,
            "-ExpectedTree",
            expected_tree,
            "-RepetitionDays",
            "1",
            "-Cycles",
            "1",
            "-HeartbeatSeconds",
            "0.2",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def test_disposable_recovery_task_plan_install_recover_uninstall(tmp_path: Path):
    if os.name != "nt":
        pytest.skip("Windows scheduled-task integration")
    task_name = f"ProjectPipelineAutonomyCampaign-C13Disp-{uuid.uuid4().hex[:10]}"
    assert task_name != LIVE_TASK
    live_before = observe_windows_scheduled_task(LIVE_TASK)
    identity = _live_identity()
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.2,
        inspect_identity=lambda _root: identity,
        finalize_commands=[],
    )
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    campaign_id = started["campaign_id"]
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 2147000000 WHERE lock_name = 'active-campaign'"
    )
    controller._db.execute(
        "UPDATE campaign_runs SET process_id = 2147000000 WHERE campaign_id = ?",
        (campaign_id,),
    )
    controller._db.execute(
        "UPDATE campaign_owner_bindings SET process_id = 2147000000 WHERE lock_name = 'active-campaign'"
    )
    controller._db.commit()
    controller.close()
    planned = _register(
        "plan",
        tmp_path,
        task_name,
        campaign_id,
        expected_sha=str(identity["sha"]),
        expected_tree=str(identity["tree"]),
    )
    assert planned["task_name"] == task_name
    assert planned["campaign_id"] == campaign_id
    assert planned["expected_sha"] == identity["sha"]
    assert planned["window_style"] == "Hidden"
    spawned = None
    try:
        installed = _register(
            "install",
            tmp_path,
            task_name,
            campaign_id,
            expected_sha=str(identity["sha"]),
            expected_tree=str(identity["tree"]),
        )
        assert installed["registered"] is True
        status = _register(
            "status",
            tmp_path,
            task_name,
            campaign_id,
            expected_sha=str(identity["sha"]),
            expected_tree=str(identity["tree"]),
        )
        assert status["registered"] is True
        assert status["hidden"] is True
        assert status["user_action_required"] is False
        pid_path = tmp_path / "logs" / "campaign.pid"
        pid_path.write_text(json.dumps({"process_id": 2147000000}) + "\n", encoding="utf-8")
        config_path = tmp_path / "logs" / "recovery_probe.json"
        probed = subprocess.run(
            [sys.executable, str(PROBE), "--config", str(config_path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"},
        )
        assert probed.returncode == 0, probed.stderr
        payload = json.loads(probed.stdout)
        assert payload["action"] == "recovered"
        assert payload["user_action_required"] is False
        if pid_path.is_file():
            pid_payload = json.loads(pid_path.read_text(encoding="utf-8"))
            spawned = pid_payload.get("process_id")
        status_path = tmp_path / "logs" / "pp385_campaign_status.json"
        assert status_path.is_file()
        after = _register(
            "status",
            tmp_path,
            task_name,
            campaign_id,
            expected_sha=str(identity["sha"]),
            expected_tree=str(identity["tree"]),
        )
        assert after["registered"] is True
    finally:
        if spawned:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_autonomy_campaign.py"),
                    "stop",
                    "--database",
                    str(tmp_path / "campaign.sqlite3"),
                    "--campaign-id",
                    campaign_id,
                    "--repository-root",
                    str(ROOT),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            )
            subprocess.run(
                ["taskkill", "/PID", str(spawned), "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        removed = _register(
            "uninstall",
            tmp_path,
            task_name,
            campaign_id,
            expected_sha=str(identity["sha"]),
            expected_tree=str(identity["tree"]),
        )
        assert removed["registered"] is False
        leftover = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert leftover.stdout.strip() == ""
        live_after = observe_windows_scheduled_task(LIVE_TASK)
        assert live_after["present"] == live_before["present"]
        assert live_after["user_action_required"] is False
        assert live_after["task_name"] == LIVE_TASK
