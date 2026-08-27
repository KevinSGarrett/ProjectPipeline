from __future__ import annotations

import subprocess
from pathlib import Path

from project_pipeline.validation.public_repository import (
    forbidden_public_paths,
    machine_specific_references,
    readme_surface_errors,
    validate_public_repository_surface,
)
from project_pipeline.validation.repository import RepositoryValidator

ROOT = Path(__file__).resolve().parents[1]


def test_current_public_repository_surface_is_valid() -> None:
    assert validate_public_repository_surface(ROOT) == []


def test_private_maintainer_paths_are_rejected(tmp_path: Path) -> None:
    private = tmp_path / "instructions"
    private.mkdir()
    (private / "00_START_HERE.md").write_text("private\n", encoding="utf-8")

    assert forbidden_public_paths(tmp_path) == ("instructions",)


def test_tracked_private_paths_are_rejected_but_ignored_residue_is_not(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("/.agents/\n", encoding="utf-8")
    ignored = tmp_path / ".agents" / "local.md"
    ignored.parent.mkdir()
    ignored.write_text("local residue\n", encoding="utf-8")
    tracked = tmp_path / "instructions" / "private.md"
    tracked.parent.mkdir()
    tracked.write_text("private control record\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".gitignore", "instructions/private.md"],
        check=True,
    )

    assert forbidden_public_paths(tmp_path) == ("instructions",)


def test_repository_validator_reports_public_surface_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "project_pipeline.validation.repository.validate_public_repository_surface",
        lambda _root: ["tracked private material"],
    )
    validator = RepositoryValidator(tmp_path)

    validator._check_public_repository_surface()

    assert [(finding.code, finding.message) for finding in validator.report.findings] == [
        ("PUBLIC003", "tracked private material")
    ]


def test_machine_specific_references_are_rejected(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "setup.md").write_text(
        r"Run the tool from C:\Project_X before continuing." "\n",
        encoding="utf-8",
    )

    assert machine_specific_references(tmp_path) == ("docs/setup.md:1",)


def test_readme_status_is_single_and_links_must_resolve(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            (
                "# ProjectPipeline",
                "## Development status",
                "## Development status",
                "[Missing](docs/missing.md)",
            )
        ),
        encoding="utf-8",
    )

    errors = readme_surface_errors(tmp_path)
    assert "README.md must contain exactly one Development status section" in errors
    assert "README.md link target is missing: docs/missing.md" in errors
