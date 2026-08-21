from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.autonomy_runtime.live_qualification import (
    StageOutcome,
    run_live_qualification,
    write_live_qualification_evidence,
)


def _scaffold_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "src" / "project_pipeline" / "github_steward").mkdir(parents=True)
    (repo / "src" / "project_pipeline" / "jira_steward").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    launcher = Path(__file__).resolve().parents[1] / "scripts" / "run_autonomy_runtime_service.py"
    (repo / "scripts" / "run_autonomy_runtime_service.py").write_text(
        launcher.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_live_qualification_passes_local_stages_and_blocks_cursor_cli(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    report = run_live_qualification(repository_root=repo, disposable_root=tmp_path / "runtime")
    by_id = {stage["stage_id"]: stage for stage in report["stages"]}
    windows = by_id["windows_service_foreground"]
    assert windows["outcome"] == StageOutcome.PASSED.value
    assert windows["observations"]["plan_valid"] is True
    assert windows["observations"]["checkpoint_status"] == "STOPPED"
    assert windows["observations"]["stale_pid_detected"] is True

    command_center = by_id["command_center_truth"]
    assert command_center["outcome"] == StageOutcome.PASSED.value
    assert command_center["observations"]["context_summary"]["source"] == "durable_state"
    assert (
        command_center["observations"]["context_summary"]["windows_service"]["checkpoint_exists"]
        is True
    )

    assert by_id["local_provider_dispatch"]["outcome"] == StageOutcome.PASSED.value

    governance = by_id["github_jira_governance"]
    assert governance["outcome"] == StageOutcome.BLOCKED_EXTERNAL.value
    assert governance["observations"]["adapters_present"] is True
    assert "github_probe" in governance["observations"]
    assert "jira_probe" in governance["observations"]
    assert "github_write_probe" in governance["observations"]
    assert "jira_write_probe" in governance["observations"]
    assert governance["observations"]["write_readback_ok"] is False

    cursor_cli = by_id["cursor_cli_provider_dispatch"]
    assert cursor_cli["outcome"] == StageOutcome.FAILED.value
    encoded = json.dumps(report)
    assert "HUMAN_REQUIRED" not in encoded
    assert "operator session" not in encoded
    assert "await human" not in encoded
    assert cursor_cli["observations"]["outcome"] == StageOutcome.FAILED.value


def test_write_live_qualification_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    output = write_live_qualification_evidence(
        repository_root=repo, disposable_root=tmp_path / "runtime"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["task_id"] == "PP-TASK-000384"
    assert output.name == "live_qualification_latest.json"
    assert payload["report_sha256"]
    assert "bound_head" in payload
    assert "bound_tree" in payload


def test_live_qualification_rerun_clears_same_disposable_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _scaffold_repo(repo)
    runtime = tmp_path / "runtime"
    first = run_live_qualification(repository_root=repo, disposable_root=runtime)
    assert first["stages"][1]["outcome"] == StageOutcome.PASSED.value
    second = run_live_qualification(repository_root=repo, disposable_root=runtime)
    assert second["stages"][1]["stage_id"] == "command_center_truth"
    assert second["stages"][1]["outcome"] == StageOutcome.PASSED.value
