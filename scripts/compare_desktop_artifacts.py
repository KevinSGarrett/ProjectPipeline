from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from project_pipeline.command_center.desktop_reproducibility import (
    compare_desktop_artifact_sets,
    load_nondeterminism_schema,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare normalized desktop artifacts")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)
    schema = load_nondeterminism_schema(args.root)
    result = compare_desktop_artifact_sets(args.left, args.right, schema)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
