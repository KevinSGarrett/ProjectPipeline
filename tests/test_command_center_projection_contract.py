from __future__ import annotations

from pathlib import Path

from project_pipeline.command_center.application_validation import (
    validate_command_center_application,
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
