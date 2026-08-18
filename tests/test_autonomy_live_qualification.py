from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.autonomy_runtime.live_qualification import (
    StageOutcome,
    run_live_qualification,
    write_live_qualification_evidence,
)


def test_live_qualification_passes_local_stages_and_blocks_cursor_cli(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src" / "project_pipeline" / "github_steward").mkdir(parents=True)
    (repo / "src" / "project_pipeline" / "jira_steward").mkdir(parents=True)
    report = run_live_qualification(repository_root=repo, disposable_root=tmp_path / "runtime")
    by_id = {stage["stage_id"]: stage for stage in report["stages"]}
    assert by_id["windows_service_foreground"]["outcome"] == StageOutcome.PASSED.value
    assert by_id["command_center_truth"]["outcome"] == StageOutcome.PASSED.value
    assert by_id["local_provider_dispatch"]["outcome"] == StageOutcome.PASSED.value
    assert by_id["github_jira_governance"]["outcome"] == StageOutcome.BLOCKED_EXTERNAL.value
    assert by_id["cursor_cli_provider_dispatch"]["outcome"] == StageOutcome.HUMAN_REQUIRED.value
    assert "pp379_writer_attestation_evidence.json" in by_id["cursor_cli_provider_dispatch"]["observations"]["missing_evidence"][0]


def test_write_live_qualification_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src" / "project_pipeline" / "github_steward").mkdir(parents=True)
    (repo / "src" / "project_pipeline" / "jira_steward").mkdir(parents=True)
    output = write_live_qualification_evidence(repository_root=repo, disposable_root=tmp_path / "runtime")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["task_id"] == "PP-TASK-000384"
    assert output.name == "live_qualification_latest.json"
