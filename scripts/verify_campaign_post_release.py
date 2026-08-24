"""Run real post-release lifecycle checks using only reacquired remote bytes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.release_factory.lifecycle import exercise_acquired_lifecycle  # noqa: E402


def _publication_binding(path: Path, *, expected_sha: str, expected_tree: str) -> dict[str, Any]:
    binding_path = path / "campaign_publication.json"
    if not binding_path.is_file():
        raise ValueError("published remote-byte acquisition lacks campaign binding")
    loaded = json.loads(binding_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("published remote-byte acquisition binding is malformed")
    if (
        loaded.get("provider") != "github-rest"
        or loaded.get("source_sha") != expected_sha
        or loaded.get("source_tree") != expected_tree
        or loaded.get("state") != "PUBLISHED"
    ):
        raise ValueError(
            "published remote-byte acquisition binding differs from campaign candidate"
        )
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--acquired-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--python-executable", default=sys.executable)
    args = parser.parse_args(argv)
    acquired = args.acquired_dir.resolve()
    try:
        binding = _publication_binding(
            acquired, expected_sha=args.expected_sha, expected_tree=args.expected_tree
        )
        report = exercise_acquired_lifecycle(
            acquired,
            args.work_dir,
            execute_native=True,
            repository_root=args.repository_root.resolve(),
            python_executable=str(args.python_executable),
        )
    except Exception as exc:
        print(json.dumps({"lifecycle": {"state": "FAILED"}, "reason": str(exc)}))
        return 1
    print(
        json.dumps(
            {
                "lifecycle": {
                    **report.model_dump(mode="json"),
                    "state": "VERIFIED",
                    "publication": binding,
                }
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
