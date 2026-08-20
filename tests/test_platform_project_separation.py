from __future__ import annotations

from pathlib import Path

from project_pipeline.io import read_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/intake/existing_python_service"


def test_platform_package_is_independent_of_portable_project_fixture() -> None:
    platform = read_json(ROOT / "config/project.json")
    assert platform["project_id"] == "PROJECT-PIPELINE"
    assert (ROOT / "src/project_pipeline").is_dir()
    assert FIXTURE.is_dir()
    assert not (FIXTURE / "src/project_pipeline").exists()
    fixture_agents = (FIXTURE / "AGENTS.md").read_text(encoding="utf-8")
    assert "Do not perform remote writes" in fixture_agents
    assert "target_local_root" in platform
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "project-pipeline"' in pyproject
    assert "existing_python_service" not in pyproject
