from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

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


def test_execute_installer_lifecycle_uses_injected_runner(tmp_path: Path) -> None:
    installer = tmp_path / "ProjectPipeline_0.10.0_x64-setup.exe"
    installer.write_bytes(b"nsis")
    target = tmp_path / "install-root"
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(list(command))
        if command[0].endswith("-setup.exe"):
            target.mkdir(parents=True, exist_ok=True)
            (target / "uninstall.exe").write_bytes(b"uninst")
        elif str(command[0]).endswith("uninstall.exe"):
            for child in target.rglob("*"):
                if child.is_file():
                    child.unlink()
        return CompletedProcess(command, 0, b"", b"")

    result = evaluate_installer_lifecycle(
        artifacts={"nsis": installer},
        predecessor=resolve_predecessor_release(tmp_path),
        execute=True,
        target_root=target,
        runner=runner,
    )
    assert result["executed"] is True
    assert result["clean_removal"] is True
    assert [step["name"] for step in result["steps"]] == [
        "clean_install",
        "repair",
        "rollback",
        "uninstall",
    ]
    assert len(calls) == 4
