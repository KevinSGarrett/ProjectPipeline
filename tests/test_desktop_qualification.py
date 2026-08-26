from __future__ import annotations

import shutil
from pathlib import Path
from subprocess import CompletedProcess

from project_pipeline.command_center.desktop_qualification import (
    NOT_APPLICABLE_NO_GOVERNED_PREDECESSOR,
    classify_desktop_artifact,
    discover_desktop_artifacts,
    evaluate_installer_lifecycle,
    observe_desktop_toolchain,
    probe_loopback_service,
    qualify_desktop_slice,
    resolve_predecessor_release,
)
from project_pipeline.validation.product_outcome import runtime_qualification_is_bound

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
    assert result["requirement_ux_0004_closed"] is runtime_qualification_is_bound(ROOT)
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
            return CompletedProcess(command, 0, b"", b"")
        if str(command[0]).endswith("uninstall.exe"):
            uninstaller = Path(command[0])
            if not uninstaller.is_file():
                raise FileNotFoundError(command[0])
            for child in target.rglob("*"):
                if child.is_file():
                    child.unlink()
            return CompletedProcess(command, 0, b"", b"")
        return CompletedProcess(command, 1, b"failed", b"")

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
    assert result["steps"][3]["reason"] == "ALREADY_REMOVED"
    assert len(calls) == 3


def test_execute_installer_lifecycle_removes_nsis_self_leftover(tmp_path: Path) -> None:
    installer = tmp_path / "ProjectPipeline_0.10.0_x64-setup.exe"
    installer.write_bytes(b"nsis")
    target = tmp_path / "install-root"

    def runner(command, **kwargs):
        if command[0].endswith("-setup.exe"):
            target.mkdir(parents=True, exist_ok=True)
            (target / "uninstall.exe").write_bytes(b"uninst")
            return CompletedProcess(command, 0, b"", b"")
        if str(command[0]).endswith("uninstall.exe"):
            return CompletedProcess(command, 0, b"", b"")
        return CompletedProcess(command, 1, b"failed", b"")

    result = evaluate_installer_lifecycle(
        artifacts={"nsis": installer},
        predecessor=resolve_predecessor_release(tmp_path),
        execute=True,
        target_root=target,
        runner=runner,
    )
    assert result["executed"] is True
    assert result["clean_removal"] is True
    assert result["remaining_files"] == []
    assert not (target / "uninstall.exe").exists()


def test_execute_installer_lifecycle_treats_removed_root_as_clean(tmp_path: Path) -> None:
    installer = tmp_path / "ProjectPipeline_0.10.0_x64-setup.exe"
    installer.write_bytes(b"nsis")
    target = tmp_path / "install-root"

    def runner(command, **kwargs):
        if command[0].endswith("-setup.exe"):
            target.mkdir(parents=True, exist_ok=True)
            (target / "uninstall.exe").write_bytes(b"uninst")
            return CompletedProcess(command, 0, b"", b"")
        if str(command[0]).endswith("uninstall.exe"):
            shutil.rmtree(target, ignore_errors=True)
            return CompletedProcess(command, 0, b"", b"")
        return CompletedProcess(command, 1, b"failed", b"")

    result = evaluate_installer_lifecycle(
        artifacts={"nsis": installer},
        predecessor=resolve_predecessor_release(tmp_path),
        execute=True,
        target_root=target,
        runner=runner,
    )
    assert result["executed"] is True
    assert result["clean_removal"] is True
    assert result["remaining_files"] == []


def test_hosted_setup_exe_is_nsis_not_native_executable(tmp_path: Path) -> None:
    hosted = tmp_path / "desktop-windows-A"
    compare = hosted / "compare"
    identity = hosted / "identity"
    compare.mkdir(parents=True)
    identity.mkdir(parents=True)
    pe = compare / "Project Pipeline Command Center.exe"
    setup = identity / "ProjectPipeline_0.10.0_x64-setup.exe"
    msi = identity / "Project Pipeline Command Center_0.10.0_x64_en-US.msi"
    pe.write_bytes(b"pe")
    setup.write_bytes(b"nsis")
    msi.write_bytes(b"msi")
    assert classify_desktop_artifact(setup) == "nsis"
    assert classify_desktop_artifact(pe) == "executable"
    assert classify_desktop_artifact(msi) == "msi"
    found = discover_desktop_artifacts(tmp_path, hosted_dir=hosted)
    assert found["executable"] == pe
    assert found["nsis"] == setup
    assert found["msi"] == msi


def test_hosted_artifacts_prefer_staged_executable_over_nested_build_helper(tmp_path: Path) -> None:
    hosted = tmp_path / "desktop-artifacts"
    staged = hosted / "project-pipeline-command-center.exe"
    helper = hosted / "cargo-target" / "release" / "build" / "crate" / "build_script_build.exe"
    staged.parent.mkdir(parents=True)
    helper.parent.mkdir(parents=True)
    staged.write_bytes(b"staged-command-center")
    helper.write_bytes(b"cargo-build-helper")

    found = discover_desktop_artifacts(tmp_path, hosted_dir=hosted)

    assert found["executable"] == staged
