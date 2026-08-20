from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from project_pipeline.command_center.desktop_qualification import qualify_desktop_slice


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observe native desktop qualification state")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)
    result = qualify_desktop_slice(args.root)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
