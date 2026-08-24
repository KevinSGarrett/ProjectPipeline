from __future__ import annotations

import json
import sys
from pathlib import Path

from project_pipeline.autonomy_runtime.command_execution import (
    command_is_allowlisted,
    command_kind,
    evaluate_command_semantics,
)
from project_pipeline.autonomy_runtime.duration_probes import required_probe_ids

ROOT = Path(__file__).resolve().parents[1]


def test_duration_probe_surface_is_broader_than_local_validation() -> None:
    required = required_probe_ids()
    assert {
        "command_center_projection",
        "autonomy_director_restart",
        "desktop_artifact_health",
        "cursor_cli_provider_dispatch",
        "github_live_readback",
        "jira_live_readback",
        "campaign_persistence_integrity",
        "recovery_isolation",
    } <= required
    assert len(required) > 5


def test_duration_probe_is_allowlisted_and_requires_subject_evidence() -> None:
    command = [sys.executable, str(ROOT / "scripts" / "campaign_duration_probe.py")]
    assert command_is_allowlisted(command, repository_root=ROOT) is True
    assert command_kind(command) == "duration-probe"
    missing_subject = evaluate_command_semantics(
        command,
        exit_code=0,
        stdout=json.dumps({"ok": True, "probe_id": "candidate_identity"}),
        expected_sha="a" * 40,
        expected_tree="b" * 40,
    )
    assert missing_subject["result"] == "FAILED"
    verified = evaluate_command_semantics(
        command,
        exit_code=0,
        stdout=json.dumps(
            {
                "ok": True,
                "probe_id": "candidate_identity",
                "subject": {
                    "sha": "a" * 40,
                    "tree": "b" * 40,
                    "clean": True,
                    "inspect_ok": True,
                },
                "evidence_sha256": "c" * 64,
            }
        ),
        expected_sha="a" * 40,
        expected_tree="b" * 40,
    )
    assert verified["result"] == "PASSED"
