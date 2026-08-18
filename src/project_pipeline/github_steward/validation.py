from __future__ import annotations

from pathlib import Path

from project_pipeline.persistence import validate_migration_catalog

_REQUIRED = (
    "src/project_pipeline/domain/github.py",
    "src/project_pipeline/github_steward/ports.py",
    "src/project_pipeline/github_steward/local_git.py",
    "src/project_pipeline/github_steward/ownership.py",
    "src/project_pipeline/github_steward/merge_gate.py",
    "src/project_pipeline/github_steward/autonomous_review.py",
    "src/project_pipeline/github_steward/protection_drift.py",
    "src/project_pipeline/github_steward/consolidation.py",
    "src/project_pipeline/github_steward/lifecycle.py",
    "src/project_pipeline/github_steward/adapter.py",
    "src/project_pipeline/github_steward/mock.py",
    "src/project_pipeline/github_steward/persistence.py",
    "src/project_pipeline/github_steward/service.py",
)


def validate_github_steward_foundation(root: Path) -> list[str]:
    errors = [
        f"repository/GitHub stewardship file is missing: {path}"
        for path in _REQUIRED
        if not (root / path).exists()
    ]
    catalog_errors = validate_migration_catalog(root)
    if catalog_errors:
        errors.extend(catalog_errors)
    return errors
