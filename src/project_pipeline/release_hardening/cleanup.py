from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROTECTED_PREFIXES = (
    "evidence/",
    "provenance/",
    "plans/",
    "jira/",
    "adr/",
    "architecture/",
    "database/",
    "release/",
)
TRANSIENT_NAMES = {"__pycache__", ".pytest_cache", "htmlcov", ".ruff_cache", ".mypy_cache"}


@dataclass(frozen=True, slots=True)
class CleanupCandidate:
    path: str
    reason: str


class CleanupPlanner:
    """Plan cleanup without deleting canonical history or traceability."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def plan(self) -> tuple[CleanupCandidate, ...]:
        rows = []
        for path in self.root.rglob("*"):
            if not path.is_dir():
                continue
            rel = path.relative_to(self.root).as_posix()
            if any(
                rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in PROTECTED_PREFIXES
            ):
                continue
            if (
                path.name in TRANSIENT_NAMES
                or rel.startswith(".local/cache")
                or rel.startswith(".local/tmp")
            ):
                rows.append(CleanupCandidate(rel, "transient generated/cache directory"))
        return tuple(sorted(rows, key=lambda row: row.path))

    @staticmethod
    def protected(relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/").lstrip("./")
        return any(
            normalized == prefix.rstrip("/") or normalized.startswith(prefix)
            for prefix in PROTECTED_PREFIXES
        )
