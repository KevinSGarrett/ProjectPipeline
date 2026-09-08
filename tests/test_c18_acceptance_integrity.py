from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from project_pipeline.assurance.published_byte_journeys import (
    run_command_center_api_journey,
    run_isolated_backup_restore_journey,
    run_persistent_director_journey,
    run_sqlite_migration_journey,
)
from project_pipeline.assurance.unattended_evidence import (
    evaluate_unattended_operating_loop_evidence,
)
from project_pipeline.autonomy_runtime.campaign import CampaignController, inspect_worktree_identity
from project_pipeline.autonomy_runtime.nonduration import evaluate_nonduration_qualification
from project_pipeline.evidence import evidence_record
from project_pipeline.release_factory.lifecycle import (
    COMMAND_CENTER_PROCESS_LIVENESS_ONLY,
    DIRECTOR_NOT_EXECUTED,
    MIGRATION_COPY_ONLY,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
TREE = "b" * 40


def _chain() -> list[dict[str, str]]:
    return [
        {"event_sha256": "1" * 64, "prev_event_sha256": None},
        {"event_sha256": "2" * 64, "prev_event_sha256": "1" * 64},
        {"event_sha256": "3" * 64, "prev_event_sha256": "2" * 64},
    ]


def _duration_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "bound_head": SHA,
        "bound_tree": TREE,
        "hash_algorithm": "sha256_canonical_file",
        "sha256": "c" * 64,
        "duration_hours": 72,
        "events": _chain(),
        "runtime_owner": "fence-1",
        "recovery_task_registered": False,
        "restart_recovery": False,
        "result": "PASS",
    }
    payload.update(overrides)
    return payload


def test_nonduration_rejects_live_verified_without_duration_evidence(tmp_path: Path) -> None:
    requirements = tmp_path / "plans" / "_traceability"
    requirements.mkdir(parents=True)
    (requirements / "requirements.jsonl").write_text(
        json.dumps(
            {
                "requirement_id": "REQ-PDEF-0011",
                "implementation_state": "LIVE_VERIFIED",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "TEST_CATALOG.json").write_text(
        json.dumps({"tests": []}), encoding="utf-8"
    )
    report = evaluate_nonduration_qualification(tmp_path)
    assert report["ok"] is False
    assert any("LIVE_VERIFIED" in item for item in report["missing"])


def test_nonduration_allows_live_verified_when_duration_evidence_is_bound(
    tmp_path: Path,
) -> None:
    requirements = tmp_path / "plans" / "_traceability"
    requirements.mkdir(parents=True)
    (requirements / "requirements.jsonl").write_text(
        json.dumps(
            {
                "requirement_id": "REQ-PDEF-0011",
                "implementation_state": "LIVE_VERIFIED",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "TEST_CATALOG.json").write_text(
        json.dumps({"tests": []}), encoding="utf-8"
    )
    report = evaluate_nonduration_qualification(
        tmp_path,
        duration_release_evidence={
            "attested_4h": True,
            "attested_24h": True,
            "attested_72h": True,
            "publication_verified": True,
        },
    )
    assert report["implementation_state"] == "LIVE_VERIFIED"
    assert report["remaining_acceptance"] == []
    assert report["duration_release_evidence_bound"] is True
    assert not any("LIVE_VERIFIED requires" in item for item in report["missing"])


def test_nonduration_still_rejects_implemented_label(tmp_path: Path) -> None:
    requirements = tmp_path / "plans" / "_traceability"
    requirements.mkdir(parents=True)
    (requirements / "requirements.jsonl").write_text(
        json.dumps(
            {
                "requirement_id": "REQ-PDEF-0011",
                "implementation_state": "IMPLEMENTED",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "TEST_CATALOG.json").write_text(
        json.dumps({"tests": []}), encoding="utf-8"
    )
    report = evaluate_nonduration_qualification(
        tmp_path,
        duration_release_evidence={
            "attested_4h": True,
            "attested_24h": True,
            "attested_72h": True,
            "publication_verified": True,
        },
    )
    assert report["ok"] is False
    assert any("cannot be IMPLEMENTED" in item for item in report["missing"])


def test_skip_worktree_hidden_bytes_make_identity_dirty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "c18@example.test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "C18"],
        check=True,
        capture_output=True,
    )
    tracked = repo / "tracked.py"
    tracked.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--skip-worktree", "tracked.py"],
        check=True,
        capture_output=True,
    )
    tracked.write_text("hidden-patch\n", encoding="utf-8")
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert porcelain.stdout.strip() == ""
    identity = inspect_worktree_identity(repo)
    assert identity["dirty"] is True
    assert identity["hidden_source_modifications"]
    assert identity["hidden_source_modifications"][0]["path"] == "tracked.py"


def test_unattended_evidence_rejects_forged_and_wrong_source() -> None:
    forged = evaluate_unattended_operating_loop_evidence(
        _duration_payload(duration_hours=1, result="PASS"),
        expected_sha=SHA,
        expected_tree=TREE,
    )
    assert forged["ok"] is False
    assert "duration_below_72h" in forged["failures"]
    assert "forged_pass_flag" in forged["failures"]
    wrong = evaluate_unattended_operating_loop_evidence(
        _duration_payload(),
        expected_sha="d" * 40,
        expected_tree=TREE,
    )
    assert "wrong_source_sha" in wrong["failures"]
    altered = evaluate_unattended_operating_loop_evidence(
        _duration_payload(),
        expected_sha=SHA,
        expected_tree=TREE,
        artifact_sha256="e" * 64,
    )
    assert "altered_evidence_bytes" in altered["failures"]
    incomplete = evaluate_unattended_operating_loop_evidence(
        _duration_payload(events=[{"event_sha256": "1" * 64, "prev_event_sha256": None}]),
        expected_sha=SHA,
        expected_tree=TREE,
    )
    assert "incomplete_event_chain" in incomplete["failures"]
    stale = evaluate_unattended_operating_loop_evidence(
        _duration_payload(runtime_owner=""),
        expected_sha=SHA,
        expected_tree=TREE,
    )
    assert "stale_runtime_ownership" in stale["failures"]
    assert stale["duration_qualified"] is False
    missing_digest = evaluate_unattended_operating_loop_evidence(
        _duration_payload(sha256=""),
        expected_sha=SHA,
        expected_tree=TREE,
        artifact_sha256="e" * 64,
    )
    assert "undeclared_evidence_digest" in missing_digest["failures"]
    assert missing_digest["duration_qualified"] is False


def test_recovery_claim_without_registered_task_is_not_a_recovery_pass() -> None:
    result = evaluate_unattended_operating_loop_evidence(
        _duration_payload(restart_recovery=True, recovery_task_registered=False),
        expected_sha=SHA,
        expected_tree=TREE,
    )
    assert result["duration_qualified"] is True
    assert result["recovery_state"] == "NOT_PROVEN"
    assert "recovery_claimed_without_registered_task" in result["failures"]
    honest = evaluate_unattended_operating_loop_evidence(
        _duration_payload(),
        expected_sha=SHA,
        expected_tree=TREE,
    )
    assert honest["duration_qualified"] is True
    assert honest["uninterrupted_duration"] is True
    assert honest["recovery_state"] == "NOT_PROVEN"


def test_evidence_record_declares_canonical_and_raw_algorithms(tmp_path: Path) -> None:
    artifact = tmp_path / "note.txt"
    artifact.write_text("hello\r\n", encoding="utf-8")
    record = evidence_record(
        evidence_id="EVID-000001",
        claim="hash semantics",
        artifact_path="note.txt",
        root=tmp_path,
        method="unit",
        result="PASS",
        verification_status="VERIFIED",
    )
    assert record["hash_algorithm"] == "sha256_canonical_file"
    assert record["sha256"] != record["sha256_raw"]


def test_lifecycle_does_not_label_unexecuted_sqlite_or_director_pass() -> None:
    assert "PASS" not in MIGRATION_COPY_ONLY
    assert "PASS" not in DIRECTOR_NOT_EXECUTED
    assert COMMAND_CENTER_PROCESS_LIVENESS_ONLY == "PROCESS_LIVENESS_ONLY"


def test_published_byte_journeys_run_in_isolation(tmp_path: Path) -> None:
    migration = run_sqlite_migration_journey(ROOT, tmp_path / "journey.sqlite3")
    assert migration["ok"] is True
    director = run_persistent_director_journey(tmp_path / "director_state.json")
    assert director["ok"] is True
    api = run_command_center_api_journey()
    assert api["ok"] is True
    restore = run_isolated_backup_restore_journey(tmp_path / "restore-workspace")
    assert restore["ok"] is True
    assert restore["cloned_authority_database"] is False


def test_reconcile_rejects_direct_sql_status_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = CampaignController(
        tmp_path / "campaign.sqlite3",
        repository_root=ROOT,
        heartbeat_seconds=1.0,
        inspect_identity=lambda _root: {"ok": True, "dirty": False},
        allow_unbound_candidate_for_tests=True,
    )
    monkeypatch.setattr(
        controller,
        "_require",
        lambda _campaign_id: {"status": "FAILED", "qualification_run_id": "QUAL-1"},
    )
    with pytest.raises(ValueError, match="direct SQL"):
        controller.reconcile_failed_finalization(
            "CAMP-TEST-000001",
            reason="publisher finalization failed after 72h attestation",
            lineage={
                "original_failure": "publication_finalization",
                "method": "direct_sql_status_update",
            },
        )
