from __future__ import annotations

from pathlib import Path

from project_pipeline.persistence import load_migration_catalog, validate_migration_catalog

_REQUIRED = (
    "src/project_pipeline/domain/control.py",
    "src/project_pipeline/control/graph.py",
    "src/project_pipeline/control/authority.py",
    "src/project_pipeline/control/kernel.py",
    "src/project_pipeline/control/persistence.py",
    "plans/03_control_and_orchestration/PLAN-CTRL-002_project_control_kernel_build_sequencer.md",
)


def validate_control_foundation(root: Path) -> list[str]:
    errors = [
        f"project-control file is missing: {path}"
        for path in _REQUIRED
        if not (root / path).exists()
    ]
    errors.extend(validate_migration_catalog(root))
    if not errors:
        catalog = load_migration_catalog(root)
        if not any(item.migration_id == "PPDB-0006" for item in catalog.migrations):
            errors.append("project-control migration PPDB-0006 is not registered")
    return errors
