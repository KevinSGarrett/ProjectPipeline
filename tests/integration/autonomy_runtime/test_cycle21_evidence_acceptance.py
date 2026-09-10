"""Cycle 21 evidence acceptance, sealer negatives, and CLI exit."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.autonomy_runtime.fleet_loop import build_parser
from project_pipeline.autonomy_runtime.fleet_loop import main as fleet_main
from project_pipeline.autonomy_runtime.observation_eval import evaluate_observation

SHA = "f41c64d5b533ed4a329e0e431ee073dd791ee050"
TREE = "66778a1fdc0a7a8d8cf3b07f25367ed896ffca2b"


def test_forged_count_only_packet_fails() -> None:
    payload = {
        "duration_met": True,
        "wall_seconds": 3600,
        "source": {"sha": SHA, "tree": TREE},
        "overlay": {"digest": "c" * 64},
        "heartbeats": [{"at_utc": f"2026-09-10T03:00:{i:02d}Z"} for i in range(60)],
        "fault": {
            "recovered": True,
            "killed": True,
            "owned_job_id": "C21-OWNED-FAULT",
            "intent_preserved": True,
            "reconcile_reason": "owned_worker_killed",
            "recovered_output_accepted": True,
            "unaffected_lane_progress": True,
            "controller_restarted": True,
        },
        "completed_jobs": [
            {
                "results": [
                    {
                        "task_id": "PP-TASK-000521",
                        "outcome": "ACCEPTED",
                        "tests_run": 0,
                        "host_id": "WIN-EVSH1DN8H5O",
                    }
                ]
            }
        ],
        "resources": {},
        "cli_ui_independent": True,
    }
    result = evaluate_observation(
        payload,
        expected_source_sha=SHA,
        expected_source_tree=TREE,
        expected_overlay_sha256="c" * 64,
    )
    assert result["ok"] is False
    assert "useful_work_missing" in result["reasons"]


def test_observe_cli_requires_evaluation_ok(tmp_path: Path, monkeypatch) -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["observe", "--duration-seconds", "1", "--json-output", str(tmp_path / "out.json")]
    )
    assert args.json_output.name == "out.json"

    def fake_observe(**kwargs: object) -> dict[str, object]:
        return {
            "ok": False,
            "duration_met": True,
            "evaluation": {"ok": False, "reasons": ["useful_work_missing"]},
            "wall_seconds": 1,
        }

    monkeypatch.setattr(
        "project_pipeline.autonomy_runtime.fleet_loop.run_observation", fake_observe
    )
    code = fleet_main(
        ["observe", "--duration-seconds", "1", "--json-output", str(tmp_path / "out.json")]
    )
    assert code == 2


def _acquired_junit(path: Path, body: bytes) -> dict[str, str]:
    path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    return {"acquired_junit_path": str(path), "artifact_sha256": digest, "junit_sha256": digest}


def test_stdout_only_forged_artifact_fails() -> None:
    payload = {
        "duration_met": True,
        "wall_seconds": 3600,
        "source": {"sha": SHA, "tree": TREE},
        "overlay": {"digest": "c" * 64},
        "heartbeats": [
            {"at_utc": datetime(2026, 9, 10, 3, i, tzinfo=UTC).isoformat()} for i in range(60)
        ],
        "fault": {
            "recovered": True,
            "killed": True,
            "owned_job_id": "C21-OWNED-FAULT",
            "intent_preserved": True,
            "reconcile_reason": "owned_worker_killed",
            "recovered_output_accepted": True,
            "unaffected_lane_progress": True,
            "controller_restarted": True,
        },
        "completed_jobs": [
            {
                "results": [
                    {
                        "task_id": "PP-TASK-000521",
                        "outcome": "ACCEPTED",
                        "tests_run": 1,
                        "artifact_sha256": "a" * 64,
                        "host_id": "WIN-EVSH1DN8H5O",
                    },
                    {
                        "task_id": "PP-TASK-000518",
                        "outcome": "ACCEPTED",
                        "tests_run": 1,
                        "artifact_sha256": "b" * 64,
                        "host_id": "COMFY-V4-CPU-01",
                    },
                ]
            }
        ],
        "resources": {
            "peak_ram_mb": 1024,
            "scratch_bytes": 2048,
            "transfer_seconds": 12.5,
            "concurrency": 2,
        },
        "cli_ui_independent": True,
    }
    result = evaluate_observation(
        payload,
        expected_source_sha=SHA,
        expected_source_tree=TREE,
        expected_overlay_sha256="c" * 64,
    )
    assert result["ok"] is False
    assert "useful_work_missing" in result["reasons"]


def test_valid_observation_shape_can_pass(tmp_path: Path) -> None:
    xeon = _acquired_junit(tmp_path / "xeon.xml", b"<testsuite tests='1' name='xeon'/>")
    comfy = _acquired_junit(tmp_path / "comfy.xml", b"<testsuite tests='1' name='comfy'/>")
    heartbeats = [
        {"at_utc": datetime(2026, 9, 10, 3, i, tzinfo=UTC).isoformat()} for i in range(60)
    ]
    payload = {
        "duration_met": True,
        "wall_seconds": 3600,
        "source": {"sha": SHA, "tree": TREE},
        "overlay": {"digest": "c" * 64},
        "heartbeats": heartbeats,
        "fault": {
            "recovered": True,
            "killed": True,
            "owned_job_id": "C21-OWNED-FAULT",
            "intent_preserved": True,
            "reconcile_reason": "owned_worker_killed",
            "recovered_output_accepted": True,
            "unaffected_lane_progress": True,
            "controller_restarted": True,
        },
        "completed_jobs": [
            {
                "results": [
                    {
                        "task_id": "PP-TASK-000521",
                        "outcome": "ACCEPTED",
                        "tests_run": 1,
                        "host_id": "WIN-EVSH1DN8H5O",
                        **xeon,
                    },
                    {
                        "task_id": "PP-TASK-000518",
                        "outcome": "ACCEPTED",
                        "tests_run": 1,
                        "host_id": "COMFY-V4-CPU-01",
                        **comfy,
                    },
                ]
            }
        ],
        "resources": {
            "peak_ram_mb": 1024,
            "scratch_bytes": 2048,
            "transfer_seconds": 12.5,
            "concurrency": 2,
        },
        "cli_ui_independent": True,
    }
    result = evaluate_observation(
        payload,
        expected_source_sha=SHA,
        expected_source_tree=TREE,
        expected_overlay_sha256="c" * 64,
        required_seconds=3600,
    )
    assert result["ok"] is True
