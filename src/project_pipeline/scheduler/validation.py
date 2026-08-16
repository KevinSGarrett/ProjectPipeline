from __future__ import annotations

from pathlib import Path

from project_pipeline.persistence import load_migration_catalog, validate_migration_catalog

_REQUIRED = (
    "src/project_pipeline/domain/scheduler.py",
    "src/project_pipeline/scheduler/engine.py",
    "src/project_pipeline/scheduler/conflicts.py",
    "src/project_pipeline/scheduler/resources.py",
    "src/project_pipeline/scheduler/persistence.py",
    "plans/04_scheduling_and_parallel_execution/PLAN-SCHED-002_dynamic_lane_scheduler_resource_governance.md",
)


def validate_scheduler_foundation(root: Path) -> list[str]:
    errors = [
        f"scheduler foundation file is missing: {path}"
        for path in _REQUIRED
        if not (root / path).exists()
    ]
    errors.extend(validate_migration_catalog(root))
    if not errors:
        catalog = load_migration_catalog(root)
        if not any(item.migration_id == "PPDB-0007" for item in catalog.migrations):
            errors.append("scheduler migration PPDB-0007 is not registered")
    return errors
