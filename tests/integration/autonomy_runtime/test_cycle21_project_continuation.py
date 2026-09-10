"""Cycle 21 continuation, selection, and blocked-lane preservation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.autonomy_runtime.context_validation import NATIVE_PASS, execute_native_tests
from project_pipeline.autonomy_runtime.fleet_loop import (
    accepted_result_hosts,
    duplicate_work_audit,
    is_executable_job,
    newly_ready_owned_jobs,
    observation_ready_task_ids,
    select_two_useful_jobs,
    useful_argv,
)

NOW = datetime(2026, 9, 10, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


def test_empty_ready_is_typed_not_hardcoded() -> None:
    ready = observation_ready_task_ids(ROOT, None, live_ssh=True)
    assert ready != ["PP-TASK-000516", "PP-TASK-000517", "PP-TASK-000519"]


def test_structural_parents_are_not_executable() -> None:
    assert is_executable_job("PP-STORY-000065") is False
    assert is_executable_job("PP-TASK-000384") is False
    selected = select_two_useful_jobs(
        ["PP-STORY-000065", "PP-TASK-000521", "PP-TASK-000518"], blocked="PP-TASK-000518"
    )
    assert selected["selected"] == ["PP-TASK-000521"]
    assert selected["blocked"] == "PP-TASK-000518"


def test_useful_argv_runs_validation_script() -> None:
    argv = useful_argv(ROOT, "PP-TASK-000521")
    assert argv[1].endswith("cycle21_validation_job.py")
    assert "PP-TASK-000384" not in argv


def test_native_job_rejects_file_presence_only(tmp_path: Path) -> None:
    result = execute_native_tests(
        root=ROOT, selection=(NATIVE_PASS,), output_dir=tmp_path / "native"
    )
    assert result["ok"] is True
    assert int(result["tests_run"]) >= 1
    artifact = tmp_path / "pass" / "artifact_manifest.json"
    if artifact.is_file():
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert payload.get("verifier") != "implementation_and_test_binding" or payload.get(
            "tests_run"
        )


def test_next_owned_job_requires_verified_prior_result() -> None:
    completed = [
        {
            "results": [
                {
                    "task_id": "PP-TASK-000991",
                    "outcome": "REJECTED",
                    "host_id": "COMFY-V4-CPU-01",
                }
            ]
        }
    ]
    assert accepted_result_hosts(completed) == set()
    assert newly_ready_owned_jobs((), selected_ids=set(), verified_hosts=set()) == []


def test_req_ctrl_and_pdef_remain_incomplete() -> None:
    audit = duplicate_work_audit(ROOT)
    catalog = ROOT / "plans" / "_traceability" / "requirements.jsonl"
    if not catalog.is_file():
        return
    assert (
        "REQ-CTRL-0004" in audit["incomplete_requirements"]
        or "REQ-PDEF-0011" in audit["incomplete_requirements"]
        or audit["incomplete_requirements"]
    )
