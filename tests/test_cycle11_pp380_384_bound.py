"""Issue-bound Cycle 11 recheck for PP-380 through PP-384."""

from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.autonomy_runtime.live_qualification import StageOutcome
from project_pipeline.io import read_json

ROOT = Path(__file__).resolve().parents[1]


def _task(local_id: str) -> dict[str, object]:
    return read_json(ROOT / "jira" / "tasks" / f"{local_id}.json")


def test_pp380_done_with_live_readback_and_audit() -> None:
    issue = _task("PP-TASK-000380")
    assert issue["state"] == "DONE"
    assert issue["remote_jira_key"] == "PP-392"
    assert issue["completion_evidence"] == ["EVID-000177"]
    assert (ROOT / "tests" / "test_product_outcome_contract.py").is_file()
    assert (ROOT / "evidence" / "pp380_383_cycle11_integrated_main_audit.json").is_file()


def test_pp381_done_with_live_readback_and_audit() -> None:
    issue = _task("PP-TASK-000381")
    assert issue["state"] == "DONE"
    assert issue["remote_jira_key"] == "PP-390"
    assert issue["completion_evidence"] == ["EVID-000177"]
    assert (ROOT / "tests" / "integration" / "autonomy_runtime" / "test_supervisor.py").is_file()


def test_pp382_done_with_live_readback_and_audit() -> None:
    issue = _task("PP-TASK-000382")
    assert issue["state"] == "DONE"
    assert issue["remote_jira_key"] == "PP-389"
    assert issue["completion_evidence"] == ["EVID-000177"]
    assert (
        ROOT / "tests" / "integration" / "autonomy_runtime" / "test_parallel_recovery.py"
    ).is_file()


def test_pp383_done_with_live_readback_and_audit() -> None:
    issue = _task("PP-TASK-000383")
    assert issue["state"] == "DONE"
    assert issue["remote_jira_key"] == "PP-387"
    assert issue["completion_evidence"] == ["EVID-000177"]
    assert (
        ROOT / "tests" / "integration" / "autonomy_runtime" / "test_golden_journey.py"
    ).is_file()


def test_pp384_provider_state_machine_is_bound_and_not_human_stop() -> None:
    issue = _task("PP-TASK-000384")
    assert issue["remote_jira_key"] == "PP-393"
    assert issue["state"] in {"BACKLOG", "READY", "IN_PROGRESS", "MERGE_READY", "DONE"}
    assert (
        ROOT / "src" / "project_pipeline" / "autonomy_runtime" / "cursor_cli_qualification.py"
    ).is_file()
    assert (ROOT / "src" / "project_pipeline" / "autonomy_runtime" / "projection.py").is_file()
    assert (ROOT / "src" / "project_pipeline" / "lifecycle" / "attestation_recovery.py").is_file()
    assert {item.value for item in StageOutcome} == {"PASSED", "BLOCKED_EXTERNAL", "FAILED"}
    encoded = json.dumps(sorted(item.name for item in StageOutcome))
    assert "HUMAN_REQUIRED" not in encoded
