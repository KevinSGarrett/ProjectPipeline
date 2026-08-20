from __future__ import annotations

from pathlib import Path

from project_pipeline.release_hardening.disposable_rehearsal import (
    RELEASE_CRITERIA,
    rehearse_disposable_candidate,
)


def test_disposable_candidate_rehearses_identity_criteria_and_rollback(tmp_path: Path) -> None:
    receipt = rehearse_disposable_candidate(tmp_path / "rc")
    candidate = receipt["candidate"]
    assert receipt["ok"] is True
    assert receipt["final_release"] is False
    assert receipt["post_deploy_state"] == "PASS"
    assert receipt["install_version"] == "1.1.0"
    assert len(candidate["source_sha"]) == 40
    assert len(candidate["source_tree"]) == 40
    assert len(receipt["immutable_identity"]) == 64
    assert set(candidate["criteria"]) == set(RELEASE_CRITERIA)
    assert all(candidate["criteria"].values())
    assert receipt["sbom"]["components"]
    assert receipt["provenance"]["archive_sha256"] == candidate["artifact_sha256"]
    assert Path(receipt["archive_path"]).is_file()
    assert all(receipt["post_deploy_checks"].values())
