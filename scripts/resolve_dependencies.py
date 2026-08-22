from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from project_pipeline.dependencies import build_environment_lock, validate_dependency_lock


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate local dependency evidence or a portable uv lock"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if not args.portable:
        build_environment_lock(root)
        errors = validate_dependency_lock(root, verify_installed=True)
        for error in errors:
            print(error, file=sys.stderr)
        return 0 if not errors else 1
    commands = [
        ["uv", "lock"],
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--output-file",
            "requirements/runtime.txt",
        ],
        [
            "uv",
            "export",
            "--locked",
            "--group",
            "test",
            "--group",
            "quality",
            "--no-emit-project",
            "--output-file",
            "requirements/development.txt",
        ],
    ]
    environment = {**os.environ, "UV_NO_MANAGED_PYTHON": "1"}
    for command in commands:
        completed = subprocess.run(command, cwd=root, env=environment, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
