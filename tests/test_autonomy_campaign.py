from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.campaign import (
    REQUIRED_PP384_STAGES,
    CampaignController,
    evaluate_pp384_admission,
    observe_windows_scheduled_task,
    verify_campaign_publication_eligibility,
)
from project_pipeline.autonomy_runtime.campaign_status import (
    CampaignStatusError,
    validate_status_projection,
)
from project_pipeline.autonomy_runtime.command_execution import (
    command_is_allowlisted,
    command_kind,
    evaluate_command_semantics,
    execute_allowlisted_command,
)
from project_pipeline.autonomy_runtime.process_identity import (
    current_process_identity,
    inspect_process,
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


def _mock_next_verified_publication(
    controller: CampaignController, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_execute = controller.execute
    consumed = False

    def execute(campaign_id: str, argv: list[str], **kwargs: object) -> dict:
        nonlocal consumed
        if not consumed:
            consumed = True
            return {
                "campaign_id": campaign_id,
                "receipt_id": "CREC-REMOTE-PUBLICATION",
                "command": list(argv),
                "executed": True,
                "result": "PASSED",
                "result_semantics": "remote-publication-verified",
                "parsed_result": {
                    "publication": {
                        "state": "PUBLISHED",
                        "draft": False,
                        "target_commitish": "a" * 40,
                        "source_tree": "b" * 40,
                        "assets": [
                            {
                                "name": "candidate.whl",
                                "sha256": "c" * 64,
                                "remote_sha256": "c" * 64,
                                "bytes_verified": True,
                            }
                        ],
                    }
                },
            }
        return original_execute(campaign_id, argv, **kwargs)

    monkeypatch.setattr(controller, "execute", execute)


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
    controller.qualification._db.execute(
        "DELETE FROM qualification_locks WHERE run_id = ?",
        (run_id,),
    )
    controller.qualification._db.commit()


def _ready_after_72h(controller: CampaignController, tmp_path: Path) -> dict:
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted4 = controller.admit_4h(started["campaign_id"])
    _seed_attested(controller, admitted4["qualification_run_id"], 4)
    admitted = controller.admit_24h(started["campaign_id"])
    _seed_attested(controller, admitted["qualification_run_id"], 24)
    hour72 = controller.admit_72h(started["campaign_id"])
    _seed_attested(controller, hour72["qualification_run_id"], 72)
    return controller._mark_72h_attested(started["campaign_id"])


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
    assert started["next_transition"] == "UNATTENDED_4_HOUR"
    admitted4 = controller.admit_4h(started["campaign_id"])
    assert admitted4["stage"] == "UNATTENDED_4_HOUR"
    assert admitted4["status"] == "RUNNING"
    with pytest.raises(ValueError, match="4-hour"):
        controller.admit_24h(started["campaign_id"])
    _seed_attested(controller, admitted4["qualification_run_id"], 4)
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
    assert admitted["stage"] == "UNATTENDED_4_HOUR"
    again = controller.advance(admitted["campaign_id"])
    assert again["stage"] == "UNATTENDED_4_HOUR"
    assert again["status"] == "RUNNING"
    controller.close()


def test_seeded_attested_24h_auto_admits_72h(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted4 = controller.admit_4h(started["campaign_id"])
    _seed_attested(controller, admitted4["qualification_run_id"], 4)
    admitted = controller.admit_24h(started["campaign_id"])
    _seed_attested(controller, admitted["qualification_run_id"], 24)
    advanced = controller.admit_72h(started["campaign_id"])
    assert advanced["stage"] == "UNATTENDED_72_HOUR"
    controller.close()


def test_timed_stage_heartbeat_runs_allowlisted_duration_probe(tmp_path: Path):
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.05,
        inspect_identity=lambda _root: _identity(),
        finalize_commands=[_probe_command()],
        duration_probe_commands=[_probe_command()],
        probe_interval_seconds=0.0,
    )
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted = controller.admit_4h(started["campaign_id"])
    beat = controller.heartbeat(admitted["campaign_id"])
    assert str(beat["last_probe"]).startswith("probe:")
    receipts = controller.receipts(admitted["campaign_id"])
    assert receipts
    assert receipts[0]["result"] == "PASSED"
    controller.close()


def test_timed_stage_failed_duration_probe_disqualifies(tmp_path: Path):
    failing = [sys.executable, str(ROOT / "scripts" / "run_autonomy_campaign.py")]
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.05,
        inspect_identity=lambda _root: _identity(),
        finalize_commands=[_probe_command()],
        duration_probe_commands=[failing],
        probe_interval_seconds=0.0,
    )
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    admitted = controller.admit_4h(started["campaign_id"])
    with pytest.raises(ValueError, match="duration probe failed"):
        controller.heartbeat(admitted["campaign_id"])
    row = controller.get(admitted["campaign_id"])
    assert row["status"] == "DISQUALIFIED"
    assert int(row["window_broken"]) == 1
    assert str(row["last_probe"]).startswith("disqualify:duration-probe-failed")
    assert row["stage"] == "UNATTENDED_4_HOUR"
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
    admitted = controller.admit_4h(started["campaign_id"])
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


def test_campaign_execute_reuses_derived_idempotency_key(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )

    first = controller.execute(started["campaign_id"], _probe_command())
    second = controller.execute(started["campaign_id"], _probe_command())

    assert second["receipt_id"] == first["receipt_id"]
    count = controller._db.execute(
        "SELECT COUNT(*) FROM campaign_command_receipts WHERE campaign_id = ?",
        (started["campaign_id"],),
    ).fetchone()[0]
    assert count == 1
    controller.close()


def test_finalize_after_seeded_72h_requires_verified_remote_publication(tmp_path: Path):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    assert ready["stage"] == "RELEASE"
    assert ready["status"] == "72H_ATTESTED"
    ready = controller.advance(ready["campaign_id"])
    assert ready["status"] == "READY_TO_PUBLISH"
    failed = controller.finalize(ready["campaign_id"], commands=[_probe_command()])
    assert failed["status"] == "FAILED"
    assert failed["stage"] == "RELEASE"
    assert failed["publication_receipts"][0]["result_semantics"] == "probe"


def test_finalize_after_seeded_72h_accepts_verified_remote_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    ready = controller.advance(_ready_after_72h(controller, tmp_path)["campaign_id"])
    _mock_next_verified_publication(controller, monkeypatch)
    published = controller.finalize(ready["campaign_id"], commands=[_probe_command()])
    assert published["status"] == "PUBLISHED"
    assert published["stage"] == "POST_RELEASE"
    assert published["publication_receipts"][0]["executed"] is True
    controller.close()


def test_campaign_publication_eligibility_requires_attested_72h(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    ready = controller.advance(_ready_after_72h(controller, tmp_path)["campaign_id"])
    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.campaign.inspect_worktree_identity",
        lambda _root: _identity(),
    )
    eligibility = verify_campaign_publication_eligibility(
        tmp_path / "campaign.sqlite3", repository_root=ROOT, campaign_id=ready["campaign_id"]
    )
    assert eligibility["attested_elapsed_seconds"] == 72 * 3600
    controller.qualification._db.execute(
        "UPDATE qualification_runs SET attested_elapsed_seconds = ? WHERE run_id = ?",
        (71 * 3600, ready["qualification_run_id"]),
    )
    controller.qualification._db.commit()
    with pytest.raises(ValueError, match="completed 72-hour qualification"):
        verify_campaign_publication_eligibility(
            tmp_path / "campaign.sqlite3", repository_root=ROOT, campaign_id=ready["campaign_id"]
        )
    controller.close()


def test_advance_auto_finalizes_after_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    _mock_next_verified_publication(controller, monkeypatch)
    monkeypatch.setattr(
        controller,
        "_default_reconcile_commands",
        lambda: [_probe_command()],
    )
    monkeypatch.setattr(
        controller,
        "_default_completion_gate_commands",
        lambda: [_probe_command()],
    )
    finalized = controller.advance(ready["campaign_id"])
    finalized = controller.advance(finalized["campaign_id"])
    finalized = controller.advance(finalized["campaign_id"])
    finalized = controller.advance(finalized["campaign_id"])
    finalized = controller.advance(finalized["campaign_id"])
    assert finalized["status"] == "FINALIZED"
    assert finalized["stage"] == "COMPLETE"
    assert finalized["completion_gate_receipts"][0]["result"] == "PASSED"
    controller.close()


def test_failed_finalize_does_not_claim_complete(tmp_path: Path):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    ready = controller.advance(ready["campaign_id"])
    failed = controller.finalize(
        ready["campaign_id"],
        commands=[[sys.executable, str(ROOT / "scripts" / "run_autonomy_campaign.py")]],
    )
    assert failed["status"] == "FAILED"
    assert failed["stage"] == "RELEASE"
    assert failed["publication_receipts"][0]["result"] == "FAILED"
    controller.close()


def test_post_release_verify_failure_marks_campaign_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    ready = controller.advance(ready["campaign_id"])
    _mock_next_verified_publication(controller, monkeypatch)
    published = controller.finalize(ready["campaign_id"], commands=[_probe_command()])
    assert published["status"] == "PUBLISHED"
    monkeypatch.setattr(
        controller,
        "_default_post_release_commands",
        lambda: [[sys.executable, str(ROOT / "scripts" / "run_autonomy_campaign.py")]],
    )
    failed = controller.advance(published["campaign_id"])
    assert failed["status"] == "FAILED"
    assert failed["stage"] == "POST_RELEASE"
    assert failed["post_release_receipts"][0]["result"] == "FAILED"
    controller.close()


def test_reconcile_failure_marks_campaign_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    ready = controller.advance(ready["campaign_id"])
    _mock_next_verified_publication(controller, monkeypatch)
    published = controller.finalize(ready["campaign_id"], commands=[_probe_command()])
    verified = controller.advance(published["campaign_id"])
    assert verified["status"] == "RECONCILING"
    monkeypatch.setattr(
        controller,
        "_default_reconcile_commands",
        lambda: [[sys.executable, str(ROOT / "scripts" / "run_autonomy_campaign.py")]],
    )
    failed = controller.advance(verified["campaign_id"])
    assert failed["status"] == "FAILED"
    assert failed["stage"] == "POST_RELEASE"
    assert failed["reconcile_receipts"][0]["result"] == "FAILED"
    controller.close()


def test_publish_to_completion_gate_transition_is_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    _mock_next_verified_publication(controller, monkeypatch)
    monkeypatch.setattr(controller, "_default_post_release_commands", lambda: [_probe_command()])
    monkeypatch.setattr(controller, "_default_reconcile_commands", lambda: [_probe_command()])
    ready = controller.advance(ready["campaign_id"])
    published = controller.advance(ready["campaign_id"])
    assert published["status"] == "PUBLISHED"
    reconciling = controller.advance(published["campaign_id"])
    assert reconciling["status"] == "RECONCILING"
    completion = controller.advance(reconciling["campaign_id"])
    assert completion["status"] == "COMPLETION_GATE"
    assert completion["stage"] == "COMPLETION_GATE"
    controller.close()


def test_schema_comes_from_catalog(tmp_path: Path):
    controller = _controller(tmp_path)
    applied = {
        str(row[0])
        for row in controller._db.execute("SELECT migration_id FROM schema_migrations").fetchall()
    }
    assert "PPDB-0022" in applied
    assert "PPDB-0023" in applied
    tables = {
        str(row[0])
        for row in controller._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {
        "campaign_runs",
        "campaign_events",
        "campaign_command_receipts",
        "campaign_locks",
        "campaign_owner_bindings",
    } <= tables
    source = (ROOT / "src/project_pipeline/autonomy_runtime/campaign.py").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS campaign_runs" not in source
    assert "apply PPDB-0022 rather than creating tables ad hoc" not in source
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


def test_production_default_commands_use_existing_cli_grammar(tmp_path: Path):
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        inspect_identity=lambda _root: _identity(),
    )
    try:
        commands = controller._default_publish_commands(
            {"campaign_id": "QCAMP-TEST", "evidence_path": str(tmp_path / "evidence")}
        )
        gate = controller._default_completion_gate_commands()
    finally:
        controller.close()
    rendered = [" ".join(item) for item in commands]
    rendered_gate = [" ".join(item) for item in gate]
    assert any(" -m project_pipeline validate --root " in row for row in rendered)
    assert any("campaign_release_publication.py" in row for row in rendered)
    assert any(
        " -m project_pipeline assurance completion-gate --root " in row for row in rendered_gate
    )
    assert all(" project_pipeline completion " not in row for row in rendered)
    assert command_kind(gate[-1]) == "assurance.completion-gate"
    assert command_is_allowlisted(gate[-1], repository_root=ROOT) is True
    assert (
        command_is_allowlisted(
            [sys.executable, "-m", "project_pipeline", "completion", "--root", str(ROOT)],
            repository_root=ROOT,
        )
        is False
    )
    missing = subprocess.run(
        [sys.executable, "-m", "project_pipeline", "completion", "--root", str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0


def test_duration_probe_default_surface_is_risk_based(tmp_path: Path):
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        inspect_identity=lambda _root: _identity(),
    )
    try:
        plan = controller._default_duration_probe_plan()
    finally:
        controller.close()
    assert controller._probe_surface_complete(plan) is True
    probe_ids = {str(item["probe_id"]) for item in plan}
    assert {
        "runtime_doctor",
        "repository_validate",
        "jira_validate",
        "control_evaluate",
        "control_sequence",
    } <= probe_ids


def test_duration_probe_surface_rejects_doctor_control_jira_only(tmp_path: Path):
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        inspect_identity=lambda _root: _identity(),
    )
    try:
        cadence = max(controller.probe_interval_seconds, controller.heartbeat_seconds)
        plan = [
            controller._build_duration_probe_entry(
                "runtime_doctor",
                [sys.executable, "-m", "project_pipeline", "doctor", "--root", str(ROOT)],
                cadence_seconds=cadence,
            ),
            controller._build_duration_probe_entry(
                "control_evaluate",
                [
                    sys.executable,
                    "-m",
                    "project_pipeline",
                    "control",
                    "evaluate",
                    "--root",
                    str(ROOT),
                ],
                cadence_seconds=cadence,
            ),
            controller._build_duration_probe_entry(
                "jira_validate",
                [sys.executable, "-m", "project_pipeline", "jira", "validate", "--root", str(ROOT)],
                cadence_seconds=cadence,
            ),
        ]
    finally:
        controller.close()
    assert controller._probe_surface_complete(plan) is False


def test_production_defaults_incomplete_cannot_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def fake_execute(argv, **_kwargs):
        kind = command_kind(argv)
        if kind == "assurance.completion-gate":
            stdout = json.dumps(
                {
                    "schema_version": "1.0.0",
                    "completion_gate": {
                        "state": "NOT_COMPLETE",
                        "final_complete": False,
                        "final_completion_gate_satisfied": False,
                    },
                }
            )
        elif kind == "control.completion":
            stdout = json.dumps(
                {
                    "completion": {
                        "schema_version": "1.0.0",
                        "state": "INCOMPLETE",
                        "final_completion_gate_satisfied": False,
                    }
                }
            )
        elif kind == "release.remote-publication":
            stdout = json.dumps(
                {
                    "publication": {
                        "state": "PUBLISHED",
                        "draft": False,
                        "target_commitish": "a" * 40,
                        "source_tree": "b" * 40,
                        "assets": [
                            {
                                "name": "candidate.whl",
                                "sha256": "c" * 64,
                                "remote_sha256": "c" * 64,
                                "bytes_verified": True,
                            }
                        ],
                    }
                }
            )
        else:
            stdout = json.dumps({"schema_version": "1.0.0", "ok": True, "errors": []})
        from project_pipeline.autonomy_runtime.command_execution import evaluate_command_semantics

        semantics = evaluate_command_semantics(argv, exit_code=0, stdout=stdout)
        result = "FAILED" if semantics["result"] == "FAILED" else "PASSED"
        digest = hashlib.sha256(json.dumps(argv, sort_keys=True).encode()).hexdigest()
        return {
            "command": list(argv),
            "command_sha256": digest,
            "cwd": str(ROOT),
            "environment_class": "test",
            "integrated_sha": "a" * 40,
            "integrated_tree": "b" * 40,
            "started_at_utc": datetime.now(UTC).isoformat(),
            "ended_at_utc": datetime.now(UTC).isoformat(),
            "exit_code": 0,
            "stdout_sha256": "b" * 64,
            "stderr_sha256": "c" * 64,
            "stdout_tail": stdout,
            "stderr_tail": "",
            "result": result,
            "result_semantics": semantics["reason"],
            "semantic_state": semantics["state"],
            "final_completion_gate_satisfied": semantics["final_completion_gate_satisfied"],
            "parsed_result": semantics["parsed"],
            "idempotency_key": f"CIDEMP-{digest[:16]}",
            "retry_disposition": "not-retried",
            "evidence_links": [],
            "executed": True,
        }

    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.campaign.execute_allowlisted_command",
        fake_execute,
    )
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=0.05,
        inspect_identity=lambda _root: _identity(),
    )
    ready = _ready_after_72h(controller, tmp_path)
    ready = controller.advance(ready["campaign_id"])
    published = controller.finalize(ready["campaign_id"])
    assert published["status"] == "PUBLISHED"
    step = controller.advance(published["campaign_id"])
    step = controller.advance(step["campaign_id"])
    finalized = controller.advance(step["campaign_id"])
    assert finalized["status"] == "FAILED"
    assert finalized["stage"] == "COMPLETION_GATE"
    kinds = [command_kind(item["command"]) for item in finalized["completion_gate_receipts"]]
    assert kinds[-1] == "assurance.completion-gate"
    last = finalized["completion_gate_receipts"][-1]
    assert last["exit_code"] == 0
    assert last["result"] == "FAILED"
    assert last["semantic_state"] != "COMPLETE"
    controller.close()


def test_stale_lock_requires_recover_not_silent_delete(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 2147000000 WHERE lock_name = 'active-campaign'"
    )
    controller._db.commit()
    second = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        inspect_identity=lambda _root: _identity(),
    )
    with pytest.raises(ValueError, match="requires recover"):
        second.start(
            state_path=tmp_path / "other",
            evidence_path=tmp_path / "evidence",
            pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
        )
    recovered = controller.recover(started["campaign_id"])
    assert recovered["campaign_id"] == started["campaign_id"]
    second.close()
    controller.close()


def test_claim_runner_rejects_second_live_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    claimed = controller.claim_runner_ownership(started["campaign_id"])
    assert int(claimed["process_id"]) == os.getpid()
    binding = controller._owner_binding()
    assert binding is not None
    foreign = {
        "process_id": 424242,
        "executable": str(binding.get("executable_identity") or "python.exe"),
        "started_at_utc": str(binding.get("process_started_at_utc")),
        "alive": True,
    }

    def fake_inspect(pid: int):
        if int(pid) == 424242:
            return foreign
        return current_process_identity() if int(pid) == os.getpid() else None

    monkeypatch.setattr("project_pipeline.autonomy_runtime.campaign.inspect_process", fake_inspect)
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 424242 WHERE lock_name = 'active-campaign'"
    )
    controller._db.execute(
        "UPDATE campaign_owner_bindings SET process_id = 424242 WHERE lock_name = 'active-campaign'"
    )
    controller._db.commit()
    other = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        inspect_identity=lambda _root: _identity(),
    )
    try:
        with pytest.raises(ValueError, match="concurrent campaign runner"):
            other.claim_runner_ownership(started["campaign_id"])
    finally:
        other.close()
    controller.close()


def test_claim_runner_rejects_reused_pid_and_recover_takes_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    reused = {
        "process_id": 424242,
        "executable": "other.exe",
        "started_at_utc": "1999-01-01T00:00:00+00:00",
        "alive": True,
    }
    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.campaign.inspect_process",
        lambda pid: reused if int(pid) == 424242 else inspect_process(int(pid)),
    )
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 424242 WHERE lock_name = 'active-campaign'"
    )
    controller._db.commit()
    other = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        inspect_identity=lambda _root: _identity(),
    )
    try:
        with pytest.raises(ValueError, match="PID was reused"):
            other.claim_runner_ownership(started["campaign_id"])
        recovered = other.recover(started["campaign_id"])
        assert recovered["campaign_id"] == started["campaign_id"]
        assert int(recovered["process_id"]) == os.getpid()
    finally:
        other.close()
        controller.close()


def test_identities_match_fails_closed_without_live_executable():
    from project_pipeline.autonomy_runtime.process_identity import identities_match

    assert (
        identities_match(
            {
                "process_id": 8,
                "executable": "C:\\Python\\python.exe",
                "started_at_utc": "2026-01-01T00:00:00+00:00",
            },
            {"process_id": 8, "executable": "", "started_at_utc": "2026-01-01T00:00:00+00:00"},
        )
        is False
    )


def test_recovery_probe_rejects_reused_pid_as_unhealthy(monkeypatch: pytest.MonkeyPatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "autonomy_campaign_recovery_probe",
        ROOT / "scripts" / "autonomy_campaign_recovery_probe.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "inspect_process",
        lambda pid: {
            "process_id": int(pid),
            "executable": "other.exe",
            "started_at_utc": "1999-01-01T00:00:00+00:00",
            "alive": True,
        },
    )
    campaign = {
        "status": "RUNNING",
        "process_id": 424242,
        "last_heartbeat_utc": datetime.now(UTC).isoformat(),
    }
    pid_identity = {
        "process_id": 424242,
        "executable": "python.exe",
        "started_at_utc": "2026-01-01T00:00:00+00:00",
    }
    binding = {
        "executable_identity": "python.exe",
        "process_started_at_utc": "2026-01-01T00:00:00+00:00",
    }
    assert module._healthy(campaign, pid_identity, 90.0, binding) is False
    assert module._healthy(campaign, {"process_id": 424242}, 90.0, None) is False
    assert (
        module._healthy(
            campaign,
            {"process_id": 424242},
            90.0,
            {"executable_identity": "", "process_started_at_utc": ""},
        )
        is False
    )


def test_missing_owner_binding_blocks_heartbeat_and_recover_takes_over(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    controller._db.execute("DELETE FROM campaign_owner_bindings")
    controller._db.commit()
    with pytest.raises(ValueError, match="requires recover"):
        controller.heartbeat(started["campaign_id"])
    recovered = controller.recover(started["campaign_id"])
    assert recovered["campaign_id"] == started["campaign_id"]
    assert controller._binding_complete(controller._owner_binding()) is True
    heartbeat = controller.heartbeat(started["campaign_id"])
    assert heartbeat["campaign_id"] == started["campaign_id"]
    controller.close()


def test_execute_and_finalize_require_live_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    controller = _controller(tmp_path)
    ready = _ready_after_72h(controller, tmp_path)
    ready = controller.advance(ready["campaign_id"])
    binding = controller._owner_binding()
    assert binding is not None
    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.campaign.inspect_process",
        lambda pid: (
            {
                "process_id": 424242,
                "executable": str(binding.get("executable_identity") or "python.exe"),
                "started_at_utc": str(binding.get("process_started_at_utc")),
                "alive": True,
            }
            if int(pid) == 424242
            else None
        ),
    )
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 424242 WHERE lock_name = 'active-campaign'"
    )
    controller._db.commit()
    with pytest.raises(ValueError, match="second runner cannot mutate"):
        controller.execute(ready["campaign_id"], _probe_command())
    with pytest.raises(ValueError, match="second runner cannot mutate"):
        controller.finalize(ready["campaign_id"], commands=[_probe_command()])
    controller.close()


def test_claim_runner_transfers_from_dead_bootstrap_pid(tmp_path: Path):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
        process_id=2147000000,
    )
    claimed = controller.claim_runner_ownership(started["campaign_id"])
    assert int(claimed["process_id"]) == os.getpid()
    lock = controller._db.execute(
        "SELECT process_id FROM campaign_locks WHERE lock_name = 'active-campaign'"
    ).fetchone()
    assert int(lock["process_id"]) == os.getpid()
    controller.close()


def test_concurrent_start_is_rejected_while_lock_owner_is_alive(tmp_path: Path):
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
    try:
        with pytest.raises(ValueError, match="concurrent campaign runner"):
            second.start(
                state_path=tmp_path / "other",
                evidence_path=tmp_path / "evidence",
                pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
            )
    finally:
        second.close()
        first.close()


def test_heartbeat_rejects_second_runner_under_live_foreign_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    binding = controller._owner_binding()
    assert binding is not None
    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.campaign.inspect_process",
        lambda pid: (
            {
                "process_id": 424242,
                "executable": str(binding.get("executable_identity") or "python.exe"),
                "started_at_utc": str(binding.get("process_started_at_utc")),
                "alive": True,
            }
            if int(pid) == 424242
            else None
        ),
    )
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 424242 WHERE lock_name = 'active-campaign'"
    )
    controller._db.commit()
    with pytest.raises(ValueError, match="second runner cannot mutate"):
        controller.heartbeat(started["campaign_id"])
    controller.close()


def test_status_projection_rejects_abbreviated_and_control_chars(tmp_path: Path):
    findings = validate_status_projection(
        {
            "integrated_sha": "9b467c8",
            "integrated_tree": "36e79ba",
            "status": "RUNNING",
            "heartbeat_fresh": True,
            "runner_owner": {"process_id": 1, "alive": False, "note": "bad\x01pid"},
            "lock_process_id": 2,
            "user_action_required": True,
            "pull_requests": [{"number": 1, "open": True, "merged": True}],
        }
    )
    assert any("abbreviated" in item for item in findings)
    assert any("ASCII control characters" in item for item in findings)
    assert any("user_action_required" in item for item in findings)
    assert any("mismatched lock PID" in item for item in findings)
    assert any("contradictory PR state" in item for item in findings)
    assert any("stale heartbeat" in item for item in findings)
    with pytest.raises(CampaignStatusError):
        from project_pipeline.autonomy_runtime.campaign_status import write_status_projection

        write_status_projection(tmp_path / "bad.json", {"integrated_sha": "short"})
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    payload = controller.project_status(
        started["campaign_id"],
        status_path=tmp_path / "status.json",
    )
    assert payload["user_action_required"] is False
    assert payload["campaign_id"] == started["campaign_id"]
    assert (tmp_path / "status.json").is_file()
    controller.close()


def test_control_completion_and_missing_completion_cli_semantics():
    missing = subprocess.run(
        [sys.executable, "-m", "project_pipeline", "completion", "--root", str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    assert (
        command_is_allowlisted(
            [sys.executable, "-m", "project_pipeline", "completion", "--root", str(ROOT)],
            repository_root=ROOT,
        )
        is False
    )
    control = [
        sys.executable,
        "-m",
        "project_pipeline",
        "control",
        "completion",
        "--root",
        str(ROOT),
    ]
    assert command_is_allowlisted(control, repository_root=ROOT) is True
    completed = subprocess.run(
        control,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"},
    )
    semantics = evaluate_command_semantics(
        control, exit_code=completed.returncode, stdout=completed.stdout or ""
    )
    assert semantics["kind"] == "control.completion"
    if semantics["result"] != "FAILED":
        assert semantics["result"] == "PARSED"
        assert semantics["state"] in {"INCOMPLETE", "COMPLETE", "BLOCKED"}
    incomplete = evaluate_command_semantics(
        [
            sys.executable,
            "-m",
            "project_pipeline",
            "assurance",
            "completion-gate",
            "--root",
            str(ROOT),
        ],
        exit_code=0,
        stdout=json.dumps(
            {
                "completion_gate": {
                    "state": "INCOMPLETE",
                    "final_complete": False,
                    "final_completion_gate_satisfied": False,
                }
            }
        ),
    )
    assert incomplete["result"] == "FAILED"
    assert incomplete["state"] == "INCOMPLETE"


def test_orchestrate_executes_allowlisted_probe(tmp_path: Path):
    store = QualificationStore(tmp_path / "qualify.sqlite3", repository_root=ROOT)
    run = store.start("RECOVERY", state_path=tmp_path / "state")
    orch = store.orchestrate(run["run_id"], [_probe_command()])
    assert orch["orchestration_receipts"][0]["executed"] is True
    assert orch["orchestration_receipts"][0]["exit_code"] == 0
    store.close()


def test_missing_owner_bindings_names_ppdb_0023_not_0022():
    from project_pipeline.autonomy_runtime.campaign import (
        CampaignSchemaError,
        required_migrations_for_missing_tables,
    )

    assert required_migrations_for_missing_tables(["campaign_owner_bindings"]) == ["PPDB-0023"]
    assert required_migrations_for_missing_tables(["campaign_runs"]) == ["PPDB-0022"]
    error = CampaignSchemaError(["campaign_owner_bindings"], ["PPDB-0023"])
    assert "PPDB-0023" in str(error)
    assert "apply PPDB-0022" not in str(error)
    assert error.next_action["user_action_required"] is False
    assert error.next_action["ad_hoc_tables_forbidden"] is True


def test_legacy_0022_copy_upgrades_to_0023_with_incomplete_identity(tmp_path: Path):
    from project_pipeline.autonomy_runtime.campaign import (
        classify_campaign_database,
        legacy_non_final_import_receipt,
    )
    from project_pipeline.persistence.migrations import SQLiteMigrationRunner

    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    runner = SQLiteMigrationRunner(connection, ROOT)
    runner.apply_all(target="PPDB-0022")
    classification = classify_campaign_database(connection)
    assert classification["latest_applied"] == "PPDB-0022"
    assert classification["migration_required"] is True
    assert classification["next_action"]["user_action_required"] is False
    assert "campaign_owner_bindings" in classification["missing_tables"]
    connection.execute(
        """
        INSERT INTO campaign_runs (
            campaign_id, integrated_sha, integrated_tree, release_identity, stage,
            qualification_run_id, fence, lease_id, process_id, service_identity,
            state_path, last_event_sha256, started_at_utc, last_heartbeat_utc,
            next_transition, retry_budget, last_probe, evidence_path,
            pp384_evidence_path, status, window_broken, prior_campaign_id, lock_token
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "QCAMP-legacy",
            "a" * 40,
            "b" * 40,
            "REL-legacy",
            "UNATTENDED_24_HOUR",
            "QRUN-legacy",
            "CFENCE-legacy",
            "CLEASE-legacy",
            51876,
            "schtasks:ProjectPipelineAutonomyCampaign",
            str(tmp_path / "state"),
            "0" * 64,
            datetime.now(UTC).isoformat(),
            datetime.now(UTC).isoformat(),
            "UNATTENDED_72_HOUR",
            2,
            "heartbeat:RUNNING",
            str(tmp_path / "evidence"),
            str(tmp_path / "pp384.json"),
            "RUNNING",
            0,
            None,
            "CLOCK-legacy",
        ),
    )
    connection.execute(
        """
        INSERT INTO campaign_locks (lock_name, campaign_id, process_id, fence, acquired_at_utc)
        VALUES ('active-campaign', 'QCAMP-legacy', 51876, 'CFENCE-legacy', ?)
        """,
        (datetime.now(UTC).isoformat(),),
    )
    connection.commit()
    runner.apply_all(target="PPDB-0023")
    assert runner.status().latest_applied == "PPDB-0023"
    after = classify_campaign_database(connection)
    assert after["migration_required"] is False
    binding = dict(
        connection.execute(
            "SELECT * FROM campaign_owner_bindings WHERE lock_name = 'active-campaign'"
        ).fetchone()
    )
    assert binding["process_id"] == 51876
    assert binding["executable_identity"] == ""
    assert binding["process_started_at_utc"] == ""
    assert CampaignController._binding_complete(binding) is False
    receipt = legacy_non_final_import_receipt(
        campaign_id="QCAMP-legacy",
        integrated_sha="a" * 40,
        integrated_tree="b" * 40,
        source_database=str(database),
        latest_applied="PPDB-0023",
    )
    assert receipt["qualifies_release"] is False
    assert receipt["admits_72_hour"] is False
    assert receipt["admits_finalization"] is False
    connection.close()


def test_recover_refuses_live_foreign_qualification_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    started = controller.admit_4h(started["campaign_id"])
    foreign = {
        "process_id": 777001,
        "executable": "python.exe",
        "started_at_utc": "2026-01-01T00:00:00+00:00",
        "alive": True,
    }

    def fake_inspect(pid: int):
        if int(pid) == 777001:
            return foreign
        if int(pid) == 51876:
            return None
        return inspect_process(int(pid))

    monkeypatch.setattr("project_pipeline.autonomy_runtime.campaign.inspect_process", fake_inspect)
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 51876 WHERE lock_name = 'active-campaign'"
    )
    controller._db.execute(
        "UPDATE qualification_locks SET process_id = 777001 WHERE lock_name = 'active-qualification'"
    )
    controller._db.commit()
    with pytest.raises(ValueError, match="live qualification owner"):
        controller.recover(started["campaign_id"])
    assert controller.get(started["campaign_id"])["status"] == "RUNNING"
    controller.close()


def test_recover_takes_over_reused_shared_qualification_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    controller = _controller(tmp_path)
    started = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
        retry_budget=2,
    )
    started = controller.admit_4h(started["campaign_id"])
    reused = {
        "process_id": 424242,
        "executable": "other.exe",
        "started_at_utc": "1999-01-01T00:00:00+00:00",
        "alive": True,
    }

    def fake_inspect(pid: int):
        if int(pid) == 424242:
            return reused
        return inspect_process(int(pid))

    monkeypatch.setattr("project_pipeline.autonomy_runtime.campaign.inspect_process", fake_inspect)
    controller._db.execute(
        "UPDATE campaign_locks SET process_id = 424242 WHERE lock_name = 'active-campaign'"
    )
    controller._db.execute(
        "UPDATE campaign_owner_bindings SET process_id = 424242 WHERE lock_name = 'active-campaign'"
    )
    controller._db.execute(
        "UPDATE qualification_locks SET process_id = 424242 WHERE lock_name = 'active-qualification'"
    )
    controller._db.commit()
    recovered = controller.recover(started["campaign_id"])
    assert recovered["campaign_id"] != started["campaign_id"]
    assert recovered["status"] == "ATTESTED"
    assert controller.get(started["campaign_id"])["status"] == "DISQUALIFIED"
    controller.close()


def test_campaign_start_is_unique_when_clock_timestamps_tie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from project_pipeline.autonomy_runtime import campaign as campaign_module

    fixed = datetime(2026, 8, 24, 8, 16, tzinfo=UTC)

    class FixedDateTime:
        @staticmethod
        def now(_tz=UTC) -> datetime:
            return fixed

        @staticmethod
        def fromisoformat(value: str) -> datetime:
            return datetime.fromisoformat(value)

    monkeypatch.setattr(campaign_module, "datetime", FixedDateTime)
    controller = _controller(tmp_path)
    first = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )
    controller.stop(first["campaign_id"], reason="test-restart")
    second = controller.start(
        state_path=tmp_path / "state",
        evidence_path=tmp_path / "evidence",
        pp384_evidence=_pp384_evidence(tmp_path / "pp384.json"),
    )

    assert second["campaign_id"] != first["campaign_id"]
    controller.close()


def test_campaign_aware_health_requires_identity_not_pid_only():
    from project_pipeline.autonomy_runtime.campaign import evaluate_campaign_aware_health

    campaign = {
        "status": "RUNNING",
        "process_id": 51876,
        "integrated_sha": "a" * 40,
        "integrated_tree": "b" * 40,
        "fence": "CFENCE-1",
        "last_heartbeat_utc": datetime.now(UTC).isoformat(),
    }
    pid_only = evaluate_campaign_aware_health(
        campaign=campaign,
        pid_identity={"process_id": 51876},
        campaign_lock_live=None,
        heartbeat_max_age_seconds=90.0,
    )
    assert pid_only["healthy"] is False
    assert "pid_only_insufficient" in pid_only["reasons"]
    assert pid_only["user_action_required"] is False

    reused = evaluate_campaign_aware_health(
        campaign=campaign,
        owner_binding={
            "executable_identity": "python.exe",
            "process_started_at_utc": "2026-01-01T00:00:00+00:00",
        },
        pid_identity={
            "process_id": 51876,
            "executable": "python.exe",
            "started_at_utc": "2026-01-01T00:00:00+00:00",
        },
        campaign_lock_live={
            "process_id": 51876,
            "executable": "other.exe",
            "started_at_utc": "1999-01-01T00:00:00+00:00",
            "alive": True,
        },
        heartbeat_max_age_seconds=90.0,
    )
    assert reused["healthy"] is False
    assert "pid_reuse" in reused["reasons"]


def test_campaign_aware_health_treats_stale_lock_and_live_child_as_one_owner():
    from project_pipeline.autonomy_runtime.campaign import evaluate_campaign_aware_health

    campaign = {
        "status": "RUNNING",
        "process_id": 51876,
        "integrated_sha": "a" * 40,
        "integrated_tree": "b" * 40,
        "fence": "CFENCE-1",
        "last_heartbeat_utc": datetime.now(UTC).isoformat(),
    }
    verdict = evaluate_campaign_aware_health(
        campaign=campaign,
        owner_binding={
            "executable_identity": "python.exe",
            "process_started_at_utc": "2026-01-01T00:00:00+00:00",
        },
        pid_identity={"process_id": 51876},
        campaign_lock_live=None,
        qualification_owner_live={
            "process_id": 21976,
            "executable": "python.exe",
            "started_at_utc": "2026-01-01T00:00:00+00:00",
            "alive": True,
        },
        expected_sha="a" * 40,
        expected_tree="b" * 40,
        expected_fence="CFENCE-1",
        heartbeat_max_age_seconds=90.0,
    )
    assert verdict["healthy"] is True
    assert verdict["owner_kind"] == "qualification_child"
    assert verdict["user_action_required"] is False

    mismatched = evaluate_campaign_aware_health(
        campaign=campaign,
        qualification_owner_live={
            "process_id": 21976,
            "executable": "python.exe",
            "started_at_utc": "2026-01-01T00:00:00+00:00",
            "alive": True,
        },
        expected_sha="c" * 40,
        heartbeat_max_age_seconds=90.0,
    )
    assert mismatched["healthy"] is False
    assert "sha_mismatch" in mismatched["reasons"]


def test_missing_live_scheduled_task_is_not_user_action() -> None:
    class _Result:
        stdout = ""
        stderr = ""
        returncode = 0

    def _runner(*_args: object, **_kwargs: object) -> _Result:
        return _Result()

    payload = observe_windows_scheduled_task(
        "ProjectPipelineAutonomyCampaign",
        runner=_runner,
    )
    assert payload["present"] is False
    assert payload["user_action_required"] is False
    assert payload["next_action"] == "defer_register_until_release_candidate"
