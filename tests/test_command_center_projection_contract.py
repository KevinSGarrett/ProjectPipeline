from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.command_center.application import RepositoryApplicationProjectionBuilder
from project_pipeline.command_center.application_validation import (
    validate_command_center_application,
)
from project_pipeline.command_center.application_verification import (
    COMMAND_CENTER_REQUIRED_SECTIONS,
)
from project_pipeline.command_center.validation import validate_command_center_foundation

ROOT = Path(__file__).resolve().parents[1]


def test_command_center_application_validation_accepts_loopback_dynamic_csp() -> None:
    errors = validate_command_center_application(ROOT)
    assert (
        "Tauri CSP must restrict Command Center API transport to the loopback control endpoint"
        not in errors
    )
    assert "Tauri CSP must not grant arbitrary remote network origins" not in errors


def test_command_center_foundation_validation_does_not_require_private_pass21_artifact() -> None:
    errors = validate_command_center_foundation(ROOT)
    assert "missing Command Center artifact: provenance/pass_21_upstream_gate.json" not in errors


def test_jira_sync_note_uses_mapped_ids_when_reconciled_keys_absent(tmp_path: Path) -> None:
    reports = tmp_path / "jira" / "reports"
    reports.mkdir(parents=True)
    (reports / "jira_sync_guard.json").write_text(
        json.dumps(
            {
                "parity_status": "PARITY_CONFIRMED",
                "mapped_ids": {
                    "PP-TASK-000385": {
                        "remote_key": "PP-391",
                        "live_status_name": "In Progress",
                    },
                    "PP-TASK-000384": {"remote_key": "PP-393", "live_status_name": "Done"},
                },
            }
        ),
        encoding="utf-8",
    )
    (reports / "live_status_snapshot.json").write_text(
        json.dumps(
            {
                "snapshot_id": "JSNAP-TEST-MAPPED-IDS",
                "status_counts": {"To Do": 1, "In Progress": 1, "Done": 1},
            }
        ),
        encoding="utf-8",
    )
    status = RepositoryApplicationProjectionBuilder(tmp_path)._jira_sync_status(3)
    assert status.stale is False
    assert "PP-391" in status.note
    assert "PP-393" in status.note
    assert "In Progress" in status.note


def test_fleet_section_is_required_for_live_command_center() -> None:
    assert "fleet" in COMMAND_CENTER_REQUIRED_SECTIONS
