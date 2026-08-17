from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), check=True, capture_output=True, text=True)


def _append_unique(path: Path, fragment: str) -> None:
    current = path.read_text(encoding="utf-8")
    if fragment in current:
        return
    path.write_text(current.rstrip() + "\n\n" + fragment.lstrip() + "\n", encoding="utf-8")


def implement(task_id: str, root: Path) -> None:
    app = root / "src" / "app.py"
    tests = root / "tests" / "test_app.py"
    if task_id == "PP-GOLDEN-001":
        _append_unique(
            app,
            "def greet(name: str) -> str:\n    return f'hello {name}'\n",
        )
        _append_unique(
            tests,
            "from src.app import greet\n\n\ndef test_greet() -> None:\n    assert greet('Ada') == 'hello Ada'\n",
        )
        return
    if task_id == "PP-GOLDEN-002":
        _append_unique(
            app,
            "def farewell(name: str) -> str:\n    return f'goodbye {name}'\n",
        )
        _append_unique(
            tests,
            "from src.app import farewell\n\n\ndef test_farewell() -> None:\n    assert farewell('Ada') == 'goodbye Ada'\n",
        )
        return
    raise SystemExit(f"unknown fixture task: {task_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    implement(args.task_id, root)
    pytest = _run([sys.executable, "-m", "pytest", "-q", "tests"], root)
    _run(["git", "add", "src/app.py", "tests/test_app.py"], root)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        _run(["git", "commit", "-m", f"implement {args.task_id}"], root)
    sha = _run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    print(f"WORKER_OK task={args.task_id} sha={sha}")
    print(pytest.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
