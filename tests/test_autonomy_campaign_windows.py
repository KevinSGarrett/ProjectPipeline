from __future__ import annotations

import json
import os
import sqlite3
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


def _runtime_environment(
    path: Path,
    database: Path,
    *,
    campaign_id: str = "QCAMP-C16B-TEST",
    candidate_sha: str = "a" * 40,
    candidate_tree: str = "b" * 40,
) -> Path:
    fence = "CFENCE-C16B-TEST"
    lease = "CLEASE-C16B-TEST"
    if database.is_file():
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT fence, lease_id FROM campaign_runs WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
        if row is not None:
            fence, lease = str(row[0]), str(row[1])
    path.write_text(
        "\n".join(
            (
                "JIRA_BASE_URL=https://example.atlassian.net",
                "JIRA_USER_EMAIL=worker@example.test",
                "JIRA_API_TOKEN_REF=dpapi://C16B_JIRA_TOKEN",
                "GITHUB_TOKEN_REF=dpapi://C16B_GITHUB_TOKEN",
                "CAMPAIGN_PROJECT_ID=PROJECT-PIPELINE",
                "CAMPAIGN_CYCLE_ID=CYCLE-16-B",
                "CAMPAIGN_MACHINE_ID=COMFY-V4-CPU-01",
                "CAMPAIGN_PRINCIPAL_SID=S-1-5-21-1000",
                f"CAMPAIGN_ID={campaign_id}",
                f"CAMPAIGN_CANDIDATE_SHA={candidate_sha}",
                f"CAMPAIGN_CANDIDATE_TREE={candidate_tree}",
                f"CAMPAIGN_SCHEDULER_LEASE_ID={lease}",
                f"CAMPAIGN_FENCE_TOKEN={fence}",
                "CAMPAIGN_CREDENTIAL_ENVELOPE_EXPIRES_AT_UTC=2099-01-01T00:00:00+00:00",
                "CAMPAIGN_DEADLINE_AT_UTC=2098-12-31T00:00:00+00:00",
                f"CAMPAIGN_DATABASE={database}",
                "",
            )
        ),
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
    runtime = _runtime_environment(tmp_path / "campaign.runtime.env", tmp_path / "campaign.sqlite3")
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
            "-CampaignId",
            "QCAMP-C16B-TEST",
            "-RuntimeEnvironmentFile",
            str(runtime),
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
    assert payload["argument_list"][1] == "run"
    # PowerShell preserves the on-disk case while Python may preserve the case
    # supplied by ``tmp_path``.  Windows paths are case-insensitive, so compare
    # the canonical case-insensitive representations rather than path spelling.
    assert os.path.normcase(payload["runtime_environment_file"]) == os.path.normcase(
        str(runtime.resolve())
    )


def test_recovery_task_plan_is_hidden_and_non_interactive(tmp_path: Path):
    text = RECOVERY.read_text(encoding="utf-8")
    assert "Register-ScheduledTask" in text
    assert "Hidden" in text
    assert "simulated_elapsed = $false" in text
    if os.name != "nt":
        return
    runtime = _runtime_environment(tmp_path / "campaign.runtime.env", tmp_path / "campaign.sqlite3")
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
            "-CampaignId",
            "QCAMP-C16B-TEST",
            "-RuntimeEnvironmentFile",
            str(runtime),
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
    assert "RuntimeEnvironmentFile" in text
    assert "New-ScheduledTaskPrincipal" in text
    assert "-LogonType Interactive" in text
    assert "-RunLevel Limited" in text
    assert "-ExecutionTimeLimit (New-TimeSpan -Minutes 4)" in text
    assert "-MultipleInstances IgnoreNew" in text
    assert "scheduled_principal_sid" in text


def test_recovery_probe_requires_a_bound_campaign_identity(tmp_path: Path):
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
        "runtime_environment_file": str(
            _runtime_environment(tmp_path / "campaign.runtime.env", tmp_path / "campaign.sqlite3")
        ),
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
    assert result.returncode != 0
    assert "requires a bound campaign ID" in result.stderr
    assert not status_path.exists()


def test_recovery_probe_rejects_a_campaign_id_mismatched_to_its_runtime(tmp_path: Path):
    config_path = tmp_path / "recovery_probe.json"
    status_path = tmp_path / "status.json"
    database = tmp_path / "campaign.sqlite3"
    payload = {
        "repository_root": str(ROOT),
        "python_exe": sys.executable,
        "database": str(database),
        "campaign_id": "QCAMP-C16B-CONFIG-MISMATCH",
        "status_path": str(status_path),
        "pid_path": str(tmp_path / "campaign.pid"),
        "log_directory": str(tmp_path),
        "heartbeat_seconds": 0.2,
        "heartbeat_max_age_seconds": 1.0,
        "runtime_environment_file": str(
            _runtime_environment(tmp_path / "campaign.runtime.env", database)
        ),
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(PROBE), "--config", str(config_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
    )
    assert result.returncode != 0
    assert "campaign ID must match" in result.stderr
    assert not status_path.exists()
    assert not database.exists()


def test_recovery_probe_preserves_a_disqualified_campaign(tmp_path: Path):
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.2,
        inspect_identity=lambda _root: _identity(),
        finalize_commands=[],
        allow_unbound_candidate_for_tests=True,
    )
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted = controller.admit_4h(started["campaign_id"])
    controller._disqualify(admitted["campaign_id"], "duration-probe-failed")
    controller.close()

    config_path = tmp_path / "recovery_probe.json"
    status_path = tmp_path / "status.json"
    config_path.write_text(
        json.dumps(
            {
                "repository_root": str(ROOT),
                "python_exe": sys.executable,
                "database": str(tmp_path / "campaign.sqlite3"),
                "campaign_id": admitted["campaign_id"],
                "expected_sha": "a" * 40,
                "expected_tree": "b" * 40,
                "fence": admitted["fence"],
                "status_path": str(status_path),
                "pid_path": str(tmp_path / "campaign.pid"),
                "log_directory": str(tmp_path),
                "heartbeat_seconds": 0.2,
                "heartbeat_max_age_seconds": 1.0,
                "runtime_environment_file": str(
                    _runtime_environment(
                        tmp_path / "campaign.runtime.env",
                        tmp_path / "campaign.sqlite3",
                        campaign_id=admitted["campaign_id"],
                    )
                ),
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(PROBE), "--config", str(config_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["action"] == "inactive"
    reopened = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.2,
        inspect_identity=lambda _root: _identity(),
        finalize_commands=[],
        allow_unbound_candidate_for_tests=True,
    )
    assert reopened.get(admitted["campaign_id"])["status"] == "DISQUALIFIED"
    assert reopened.current_running_campaigns() == []
    reopened.close()


def _register(
    action: str,
    tmp_path: Path,
    task_name: str,
    campaign_id: str = "",
    *,
    expected_sha: str = "a" * 40,
    expected_tree: str = "b" * 40,
) -> dict:
    runtime = _runtime_environment(
        tmp_path / "campaign.runtime.env",
        tmp_path / "campaign.sqlite3",
        campaign_id=campaign_id or "QCAMP-C16B-TEST",
        candidate_sha=expected_sha,
        candidate_tree=expected_tree,
    )
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
            "-RuntimeEnvironmentFile",
            str(runtime),
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
        assert status["enabled"] is True
        assert status["hidden"] is True
        assert status["principal_identity"]
        assert status["scheduled_principal_sid"].startswith("S-")
        assert status["principal_sid"] == status["scheduled_principal_sid"]
        assert status["principal_sid_matches_expected"] is True
        assert status["principal_identity_matches_expected"] is True
        assert status["principal_logon_type"] == "Interactive"
        assert status["principal_run_level"] == "Limited"
        assert Path(status["action_executable"]).resolve() == Path(sys.executable).resolve()
        assert Path(status["working_directory"]).resolve() == ROOT
        assert "autonomy_campaign_recovery_probe.py" in status["action_arguments"]
        assert status["execution_time_limit"] == "PT4M"
        assert status["multiple_instances"] == "IgnoreNew"
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
        recovered_campaign_id = payload["campaign_id"]
        updated_config = json.loads(config_path.read_text(encoding="utf-8"))
        assert updated_config["campaign_id"] == recovered_campaign_id
        if recovered_campaign_id != campaign_id:
            assert updated_config["fence"]
        else:
            assert updated_config["fence"] == ""
        if pid_path.is_file():
            pid_payload = json.loads(pid_path.read_text(encoding="utf-8"))
            spawned = pid_payload.get("process_id")
        status_path = tmp_path / "logs" / "pp385_campaign_status.json"
        assert status_path.is_file()
        after = _register(
            "status",
            tmp_path,
            task_name,
            recovered_campaign_id,
            expected_sha=str(identity["sha"]),
            expected_tree=str(identity["tree"]),
            # A read-only task status must leave the dynamically retargeted
            # recovery binding intact.
        )
        assert after["registered"] is True
        assert (
            json.loads(config_path.read_text(encoding="utf-8"))["campaign_id"]
            == recovered_campaign_id
        )
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
                    recovered_campaign_id,
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
