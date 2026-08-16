from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and verify a local Project Pipeline checkout"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--profile", default="local")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    environment = {**os.environ, "PYTHONPATH": str(root / "src")}
    commands = [
        [
            sys.executable,
            "-m",
            "project_pipeline",
            "bootstrap",
            "--root",
            str(root),
            "--profile",
            args.profile,
            "--prepare",
        ],
        [
            sys.executable,
            "-m",
            "project_pipeline",
            "dependencies",
            "validate",
            "--root",
            str(root),
            "--verify-installed",
        ],
        [
            sys.executable,
            "-m",
            "project_pipeline",
            "schemas",
            "check",
            "--root",
            str(root),
        ],
    ]
    if not args.skip_tests:
        commands.append([sys.executable, "-m", "pytest", "-q"])

    for command in commands:
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
