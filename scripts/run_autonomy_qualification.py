from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_pipeline.autonomy_runtime.qualification import QualificationStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Start or resume an unattended qualification run")
    parser.add_argument("action", choices=("start", "heartbeat", "resume", "health", "fail"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--stage", choices=("RECOVERY", "UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"))
    parser.add_argument("--run-id")
    parser.add_argument("--reason", default="operator-stop")
    args = parser.parse_args()
    store = QualificationStore(args.database)
    try:
        if args.action == "start":
            if args.stage is None or args.state_path is None:
                raise SystemExit("start requires --stage and --state-path")
            result = store.start(args.stage, state_path=args.state_path)
        elif args.action == "heartbeat":
            result = store.heartbeat(str(args.run_id))
        elif args.action == "resume":
            result = store.resume(str(args.run_id))
        elif args.action == "fail":
            result = store.fail(str(args.run_id), reason=args.reason)
        else:
            result = store.health(str(args.run_id))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
