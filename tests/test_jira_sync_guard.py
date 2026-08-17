from __future__ import annotations

import json
import shutil
from pathlib import Path

from project_pipeline.jira_steward.sync_guard import evaluate_jira_sync_guard

ROOT = Path(__file__).resolve().parents[1]


def test_jira_sync_guard_passes_for_repository_state() -> None:
    result = evaluate_jira_sync_guard(ROOT)
    assert result.passes is True, result.reasons


def test_jira_sync_guard_blocks_when_artifact_missing(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "jira", tmp_path / "jira")
    artifact = tmp_path / "jira" / "reports" / "jira_sync_guard.json"
    artifact.unlink()

    result = evaluate_jira_sync_guard(tmp_path)
    assert result.passes is False
    assert any("missing" in reason for reason in result.reasons)


def test_jira_sync_guard_blocks_when_fingerprint_stale(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "jira", tmp_path / "jira")
    artifact = tmp_path / "jira" / "reports" / "jira_sync_guard.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["local_mirror_fingerprint"] = "0" * 64
    artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    result = evaluate_jira_sync_guard(tmp_path)
    assert result.passes is False
    assert any("stale" in reason for reason in result.reasons)
