from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.campaign import (
    REQUIRED_PP384_STAGES,
    CampaignController,
    evaluate_pp384_admission,
)
from project_pipeline.autonomy_runtime.command_execution import (
    command_is_allowlisted,
    execute_allowlisted_command,
)
from project_pipeline.autonomy_runtime.qualification import QualificationStore

ROOT = Path(__file__).resolve().parents[1]


def _pp384_evidence(path: Path, *, failed_stage: str | None = None) -> Path:
    stages = []
    for stage_id in REQUIRED_PP384_STAGES:
        outcome = "FAILED" if stage_id == failed_stage else "PASSED"
        stages.append({"stage_id": stage_id, "outcome": outcome, "reasons": [], "observations": {}})
    payload = {
        "schema_version": "1.0.0",
        "task_id": "PP-TASK-000384",
        "stages": stages,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _identity(sha: str = "a" * 40, tree: str = "b" * 40, dirty: bool = False) -> dict:
    return {"sha": sha, "tree": tree, "dirty": dirty, "ok": True}


def _probe_command() -> list[str]:
    return [sys.executable, str(ROOT / "scripts" / "campaign_probe.py")]


def _controller(tmp_path: Path, inspect=None) -> CampaignController:
    return CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.05,
        inspect_identity=inspect or (lambda _root: _identity()),
        finalize_commands=[_probe_command()],
    )


def _seed_attested(controller: CampaignController, run_id: str, hours: int) -> None:
    controller.qualification._db.execute(
        """
        UPDATE qualification_runs
        SET status = 'ATTESTED', window_broken = 0, attested_elapsed_seconds = ?,
            last_heartbeat_utc = ?
        WHERE run_id = ?
        """,
        (hours * 3600, datetime.now(UTC).isoformat(), run_id),
    )
    controller.qualification._db.commit()


def _ready_after_72h(controller: CampaignController, tmp_path: Path) -> dict:
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted = controller.admit_24h(started["campaign_id"])
    _seed_attested(controller, admitted["qualification_run_id"], 24)
    hour72 = controller.admit_72h(started["campaign_id"])
    _seed_attested(controller, hour72["qualification_run_id"], 72)
    return controller._mark_ready_to_finalize(started["campaign_id"])


def test_pp384_admission_requires_all_five_stages(tmp_path: Path):
    good = _pp384_evidence(tmp_path / "good.json")
    assert evaluate_pp384_admission(good)["admitted"] is True
    bad = _pp384_evidence(tmp_path / "bad.json", failed_stage="cursor_cli_provider_dispatch")
    assert evaluate_pp384_admission(bad)["admitted"] is False


def test_campaign_rejects_dirty_worktree_and_failed_pp384(tmp_path: Path):
    evidence = _pp384_evidence(tmp_path / "pp384.json")
    dirty = _controller(tmp_path, inspect=lambda _root: _identity(dirty=True))
    with pytest.raises(ValueError, match="clean immutable worktree"):
        dirty.start(
            state_path=tmp_path / "state",
            evidence_path=tmp_path / "evidence",
            pp384_evidence=evidence,
        )
    dirty.close()
    failed = _controller(tmp_path / "b")
    with pytest.raises(ValueError, match="PP-384"):
        failed.start(
            state_path=tmp_path / "state",
            evidence_path=tmp_path / "evidence",
            pp384_evidence=_pp384_evidence(
                tmp_path / "fail.json", failed_stage="github_jira_governance"
            ),
        )
    failed.close()


def test_campaign_runs_recovery_and_admits_24h(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
        service_identity="pid-test",
    )
    assert started["stage"] == "RECOVERY"
    assert started["status"] == "ATTESTED"
    assert started["integrated_sha"] == "a" * 40
    assert started["fence"].startswith("CFENCE-")
    assert started["lease_id"].startswith("CLEASE-")
    assert started["next_transition"] == "UNATTENDED_24_HOUR"
    admitted = controller.admit_24h(started["campaign_id"])
    assert admitted["stage"] == "UNATTENDED_24_HOUR"
    assert admitted["status"] == "RUNNING"
    with pytest.raises(ValueError, match="24-hour"):
        controller.admit_72h(started["campaign_id"])
    controller.close()


def test_advance_does_not_shorten_24h(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted = controller.advance(started["campaign_id"])
    assert admitted["stage"] == "UNATTENDED_24_HOUR"
    again = controller.advance(admitted["campaign_id"])
    assert again["stage"] == "UNATTENDED_24_HOUR"
    assert again["status"] == "RUNNING"
    controller.close()


def test_seeded_attested_24h_auto_admits_72h(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted = controller.admit_24h(started["campaign_id"])
    _seed_attested(controller, admitted["qualification_run_id"], 24)
    advanced = controller.admit_72h(started["campaign_id"])
    assert advanced["stage"] == "UNATTENDED_72_HOUR"
    controller.close()


def test_identity_drift_disqualifies(tmp_path: Path):
    current = {"value": _identity()}

    def inspect(_root: Path) -> dict:
        return current["value"]

    controller = _controller(tmp_path, inspect=inspect)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    current["value"] = _identity(sha="c" * 40)
    with pytest.raises(ValueError, match="identity drifted"):
        controller.heartbeat(started["campaign_id"])
    assert controller.get(started["campaign_id"])["status"] == "DISQUALIFIED"
    controller.close()


def test_clock_rollback_and_fence_mismatch_disqualify(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    campaign_id = started["campaign_id"]
    controller._db.execute(
        "UPDATE campaign_runs SET last_heartbeat_utc = ? WHERE campaign_id = ?",
        ((datetime.now(UTC) + timedelta(hours=2)).isoformat(), campaign_id),
    )
    controller._db.commit()
    with pytest.raises(ValueError, match="clock rollback"):
        controller.heartbeat(campaign_id)
    controller.close()

    controller = _controller(tmp_path / "fence")
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    with pytest.raises(ValueError, match="fence mismatch"):
        controller.heartbeat(started["campaign_id"], fence="CFENCE-forged")
    assert controller.get(started["campaign_id"])["status"] == "DISQUALIFIED"
    controller.close()


def test_stale_timed_runner_preserves_disqualified_and_starts_fresh(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
        retry_budget=2,
    )
    admitted = controller.admit_24h(started["campaign_id"])
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 2147000000 WHERE lock_name = 'active-campaign'"
    )
    controller._db.commit()
    recovered = controller.recover(admitted["campaign_id"])
    assert recovered["campaign_id"] != admitted["campaign_id"]
    assert recovered["prior_campaign_id"] == admitted["campaign_id"]
    assert controller.get(admitted["campaign_id"])["status"] == "DISQUALIFIED"
    assert recovered["retry_budget"] == 1
    controller.close()


def test_allowlist_rejects_untrusted_and_executes_probe(tmp_path: Path):
    probe = [
        sys.executable,
        str(ROOT / "scripts" / "campaign_probe.py"),
    ]
    assert command_is_allowlisted(probe, repository_root=ROOT) is True
    assert command_is_allowlisted(["cmd.exe", "/c", "echo pwn"], repository_root=ROOT) is False
    assert (
        command_is_allowlisted([sys.executable, "-c", "print('nope')"], repository_root=ROOT)
        is False
    )
    receipt = execute_allowlisted_command(
        probe, cwd=ROOT, repository_root=ROOT, idempotency_key="CIDEMP-probe"
    )
    assert receipt["executed"] is True
    assert receipt["exit_code"] == 0
    assert receipt["result"] == "PASSED"
    assert "campaign" in receipt["stdout_tail"]


def test_campaign_execute_persists_truthful_receipt(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    receipt = controller.execute(started["campaign_id"], _probe_command())
    assert receipt["executed"] is True
    stored = controller.receipts(started["campaign_id"])
    assert stored[0]["exit_code"] == 0
    assert stored[0]["command_sha256"] == receipt["command_sha256"]
    with pytest.raises(ValueError, match="allowlist"):
        controller.execute(started["campaign_id"], ["powershell", "-Command", "Get-Process"])
    controller.close()


def test_finalize_after_seeded_72h(tmp_path: Path):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    assert ready["stage"] == "RELEASE"
    finalized = controller.finalize(ready["campaign_id"], commands=[_probe_command()])
    assert finalized["status"] == "FINALIZED"
    assert finalized["stage"] == "COMPLETE"
    assert finalized["finalization_receipts"][0]["executed"] is True
    controller.close()


def test_advance_auto_finalizes_after_ready(tmp_path: Path):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    finalized = controller.advance(ready["campaign_id"])
    assert finalized["status"] == "FINALIZED"
    assert finalized["stage"] == "COMPLETE"
    assert finalized["finalization_receipts"][0]["result"] == "PASSED"
    controller.close()


def test_failed_finalize_does_not_claim_complete(tmp_path: Path):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    failed = controller.finalize(
        ready["campaign_id"],
        commands=[[sys.executable, str(ROOT / "scripts" / "run_autonomy_campaign.py")]],
    )
    assert failed["status"] == "FAILED"
    assert failed["stage"] == "RELEASE"
    assert failed["finalization_receipts"][0]["result"] == "FAILED"
    controller.close()


def test_schema_comes_from_catalog(tmp_path: Path):
    controller = _controller(tmp_path)
    applied = {
        str(row[0])
        for row in controller._db.execute("SELECT migration_id FROM schema_migrations").fetchall()
    }
    assert "PPDB-0022" in applied
    tables = {
        str(row[0])
        for row in controller._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"campaign_runs", "campaign_events", "campaign_command_receipts", "campaign_locks"} <= (
        tables
    )
    source = (ROOT / "src/project_pipeline/autonomy_runtime/campaign.py").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS campaign_runs" not in source
    controller.close()


def test_concurrent_campaign_rejected(tmp_path: Path):
    first = _controller(tmp_path)
    first.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    second = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        inspect_identity=lambda _root: _identity(),
    )
    with pytest.raises(ValueError, match="concurrent campaign"):
        second.start(
            state_path=tmp_path / "other",
            evidence_path=tmp_path / "evidence",
            pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
        )
    first.close()
    second.close()


def test_health_reports_no_simulated_elapsed(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    health = controller.health(started["campaign_id"])
    assert health["simulated_elapsed"] is False
    assert "recover" in " ".join(health["resume_command"])
    assert health["identity_drift"] is False
    controller.close()


def test_cli_health_and_stop(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    campaign_id = started["campaign_id"]
    controller.close()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    database = tmp_path / "campaign.sqlite3"
    health = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_autonomy_campaign.py"),
            "health",
            "--database",
            str(database),
            "--campaign-id",
            campaign_id,
            "--repository-root",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    assert json.loads(health.stdout)["campaign_id"] == campaign_id
    stopped = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_autonomy_campaign.py"),
            "stop",
            "--database",
            str(database),
            "--campaign-id",
            campaign_id,
            "--repository-root",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    assert json.loads(stopped.stdout)["status"] == "STOPPED"


def test_inspect_worktree_identity_reports_git_fields():
    from project_pipeline.autonomy_runtime.campaign import inspect_worktree_identity

    identity = inspect_worktree_identity(ROOT)
    assert identity["ok"] is True
    assert len(identity["sha"]) == 40
    assert len(identity["tree"]) == 40


def test_orchestrate_executes_allowlisted_probe(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    run = store.start("RECOVERY", state_path=tmp_path / "state")
    orch = store.orchestrate(run["run_id"], [_probe_command()])
    assert orch["orchestration_receipts"][0]["executed"] is True
    assert orch["orchestration_receipts"][0]["exit_code"] == 0
    store.close()
