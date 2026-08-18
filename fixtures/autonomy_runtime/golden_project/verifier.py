from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    observed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=str(root),
        check=False,
        capture_output=True,
        text=True,
    )
    digest = hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest()
    if completed.returncode != 0:
        print(f"VERIFIER_FAIL sha={observed} exit={completed.returncode} stdout_sha256={digest}")
        return completed.returncode
    print(f"VERIFIER_OK sha={observed} stdout_sha256={digest} verifier=golden-independent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
