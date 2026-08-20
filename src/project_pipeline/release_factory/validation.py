from __future__ import annotations

from pathlib import Path

_REQUIRED = (
    "src/project_pipeline/release_factory/__init__.py",
    "src/project_pipeline/release_factory/version.py",
    "src/project_pipeline/release_factory/bundle.py",
    "src/project_pipeline/release_factory/supply.py",
    "src/project_pipeline/release_factory/lifecycle.py",
    "src/project_pipeline/github_steward/draft_release.py",
    "docs/release/draft_release_factory.md",
)


def validate_release_factory(root: Path) -> list[str]:
    return [
        f"release factory file is missing: {path}"
        for path in _REQUIRED
        if not (root / path).is_file()
    ]
