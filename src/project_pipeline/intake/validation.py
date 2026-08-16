from __future__ import annotations

from pathlib import Path

from project_pipeline.domain import IntakeMode, ProjectIntakeRequest, ProjectProfile
from project_pipeline.intake.compiler import compile_project

_REQUIRED_PATHS = (
    "src/project_pipeline/domain/intake.py",
    "src/project_pipeline/intake/discovery.py",
    "src/project_pipeline/intake/profiles.py",
    "src/project_pipeline/intake/mapping.py",
    "src/project_pipeline/intake/gaps.py",
    "src/project_pipeline/intake/compiler.py",
    "src/project_pipeline/intake/bootstrap.py",
    "src/project_pipeline/services/intake.py",
    "database/migrations/sqlite/PPDB-0003_project_intake_compilation.up.sql",
    "database/migrations/sqlite/PPDB-0003_project_intake_compilation.down.sql",
    "schemas/project_intake_request.schema.json",
    "schemas/repository_discovery.schema.json",
    "schemas/compiled_project_manifest.schema.json",
    "fixtures/intake/existing_python_service/pyproject.toml",
)


def validate_intake_foundation(root: Path) -> list[str]:
    """Validate the source-controlled intake/compiler foundation without external access."""

    errors: list[str] = []
    for relative in _REQUIRED_PATHS:
        if not (root / relative).is_file():
            errors.append(f"required intake asset is missing: {relative}")
    fixture = root / "fixtures/intake/existing_python_service"
    if not fixture.is_dir():
        return errors
    try:
        request = ProjectIntakeRequest(
            mode=IntakeMode.EXISTING_PROJECT,
            project_name="Example Service",
            target_root=str(fixture),
        )
        first = compile_project(request)
        second = compile_project(request)
    except Exception as error:
        errors.append(
            f"intake self-check could not compile the representative fixture: "
            f"{type(error).__name__}: {error}"
        )
        return errors
    if first.compilation_id != second.compilation_id:
        errors.append("unchanged fixture compilation is not deterministic")
    if first.primary_profile is not ProjectProfile.PYTHON_SERVICE:
        errors.append("representative Python service profile was not detected")
    if "DISCOVERY_IS_READ_ONLY" not in first.operating_constraints:
        errors.append("compiled manifest lacks the read-only discovery constraint")
    if "HUMAN_AUTHORED_AUTHORITIES_ARE_NOT_OVERWRITTEN" not in first.operating_constraints:
        errors.append("compiled manifest lacks the no-overwrite authority constraint")
    if not first.repository_map.entries:
        errors.append("representative repository map is empty")
    if not any(item.tested_by for item in first.repository_map.entries):
        errors.append("representative repository map lacks source-to-test relationships")
    return errors
