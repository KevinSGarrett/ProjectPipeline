from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def resolve_repository_identity(root: Path) -> tuple[str, str]:
    """Return the exact current HEAD SHA and tree. Fail closed on abbreviated identity."""

    def _rev_parse(argument: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", argument],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
        value = (completed.stdout or "").strip().lower()
        if completed.returncode != 0 or not _FULL_SHA.fullmatch(value):
            raise ValueError(f"current repository SHA/tree could not be resolved ({argument})")
        return value

    return _rev_parse("HEAD"), _rev_parse("HEAD^{tree}")
