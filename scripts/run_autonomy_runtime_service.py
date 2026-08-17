from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.windows_service import (  # noqa: E402
    AutonomyRuntimeWindowsService,
    build_paths,
    plan_service_commands,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--working-directory", type=Path)
    parser.add_argument("--max-seconds", type=float)
    args = parser.parse_args()
    root = (args.working_directory or args.root).resolve()
    paths = build_paths(root=root, state_path=args.state, log_path=args.log)
    service = AutonomyRuntimeWindowsService(paths)
    if args.plan:
        print(json.dumps(plan_service_commands(paths, Path(__file__)), indent=2, sort_keys=True))
        return 0
    if args.status:
        print(json.dumps(service.health(), indent=2, sort_keys=True))
        return 0
    if args.foreground:
        return service.run_foreground(max_seconds=args.max_seconds)
    parser.error("choose --foreground, --status, or --plan")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
