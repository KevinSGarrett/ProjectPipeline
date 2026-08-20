from __future__ import annotations

from pathlib import Path

from project_pipeline.command_center.desktop_qualification import (
    NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR,
    evaluate_installer_lifecycle,
    observe_desktop_toolchain,
    probe_loopback_service,
    qualify_desktop_slice,
    resolve_predecessor_release,
)

ROOT = Path(__file__).resolve().parents[1]


def test_toolchain_observation_is_measured_not_hardcoded() -> None:
    observed = observe_desktop_toolchain()
    assert "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT" not in str(observed)
    assert observed["os_identity_present"] is True
    assert "rustc_path" in observed
    assert "npm_path" in observed


def test_predecessor_absence_is_not_upgrade_credit(tmp_path: Path) -> None:
    predecessor = resolve_predecessor_release(tmp_path)
    assert predecessor["status"] == NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR
    plan = evaluate_installer_lifecycle(artifacts={}, predecessor=predecessor)
    assert plan["executed"] is False
    assert plan["upgrade_credit"] is False
    assert "clean_install" in plan["planned_sequence"]


def test_qualify_desktop_slice_reports_lockfiles_and_keeps_ux_open() -> None:
    result = qualify_desktop_slice(ROOT)
    assert result["lockfiles"]["npm"] is True
    assert result["lockfiles"]["cargo"] is True
    assert result["requirement_ux_0004_closed"] is False
    assert result["installer_lifecycle"]["upgrade_credit"] is False


def test_loopback_probe_does_not_raise() -> None:
    assert probe_loopback_service(port=1) is False
