from __future__ import annotations

from pathlib import Path

from project_pipeline.autonomy_runtime.windows_service import (
    AutonomyRuntimeWindowsService,
    build_paths,
    plan_service_commands,
    probe_namespaced_windows_service,
    quote_windows,
)


def test_windows_quoting_and_command_plan(tmp_path: Path) -> None:
    assert quote_windows("plain") == "plain"
    assert quote_windows(r"C:\Program Files\app.exe") == r'"C:\Program Files\app.exe"'
    paths = build_paths(root=tmp_path / "svc root")
    plan = plan_service_commands(paths, Path("scripts/run_autonomy_runtime_service.py"))
    assert "sc.exe" in plan["install"]
    assert paths.service_name in plan["status"]
    assert "binPath=" in plan["install"]
    assert "secret" not in plan["install"].lower()
    assert str(paths.working_directory) in plan["install"] or "svc" in plan["install"]


def test_foreground_lifecycle_and_stale_pid(tmp_path: Path) -> None:
    paths = build_paths(root=tmp_path)
    service = AutonomyRuntimeWindowsService(paths)
    assert service.run_foreground(max_seconds=0.1) == 0
    health = service.health()
    assert health["pid"] is None
    paths.pid_path.write_text("999999", encoding="utf-8")
    assert service.health()["stale_pid"] is True
    missing = build_paths(root=tmp_path / "missing", executable=tmp_path / "no-python.exe")
    assert AutonomyRuntimeWindowsService(missing).run_foreground(max_seconds=0.1) == 2


def test_namespaced_windows_service_probe_does_not_leave_residue() -> None:
    namespaced = build_paths(root=Path("."), service_name="ProjectPipelineCycle015Probe")
    assert namespaced.service_name == "ProjectPipelineCycle015Probe"
    result = probe_namespaced_windows_service(namespaced.service_name)
    assert result["attempted"] is True
    assert result["service_name"].startswith("ProjectPipelineCycle")
    if result.get("installed"):
        assert result.get("cleaned") is True
    else:
        assert result.get("precondition") in {
            None,
            "MACHINE_PRECONDITION_ELEVATION_UNAVAILABLE",
        }
