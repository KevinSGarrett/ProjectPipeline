from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from project_pipeline.autonomy_runtime.qualification import QualificationStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate the unattended qualification runner")
    parser.add_argument(
        "action",
        choices=(
            "recovery-drill",
            "start",
            "run",
            "status",
            "health",
            "heartbeat",
            "stop",
            "fail",
            "resume",
            "attest",
            "complete",
            "orchestrate",
        ),
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--stage", choices=("RECOVERY", "UNATTENDED_24_HOUR", "UNATTENDED_72_HOUR"))
    parser.add_argument("--run-id")
    parser.add_argument("--reason", default="operator-stop")
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--cycles", type=int, default=0)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument(
        "--command-json", help="JSON list of command argument lists for orchestrate"
    )
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()
    store = QualificationStore(
        args.database,
        repository_root=args.repository_root,
        heartbeat_seconds=args.heartbeat_seconds,
    )
    try:
        result = _dispatch(store, args)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        store.close()


def _dispatch(store: QualificationStore, args: argparse.Namespace) -> dict:
    if args.action == "recovery-drill":
        if args.state_path is None:
            raise SystemExit("recovery-drill requires --state-path")
        return store.recovery_drill(state_path=args.state_path)
    if args.action == "start":
        if args.stage is None or args.state_path is None:
            raise SystemExit("start requires --stage and --state-path")
        return store.start(args.stage, state_path=args.state_path)
    if args.action == "run":
        run_id = args.run_id
        if run_id is None:
            if args.stage is None or args.state_path is None:
                raise SystemExit("run requires --run-id or --stage and --state-path")
            run_id = store.start(args.stage, state_path=args.state_path)["run_id"]
        cycles = args.cycles
        last = store.health(run_id)
        count = 0
        while True:
            if args.stop_file is not None and args.stop_file.exists():
                return store.stop(run_id, reason="stop-file")
            last = store.heartbeat(run_id)
            count += 1
            if cycles > 0 and count >= cycles:
                return last
            time.sleep(args.heartbeat_seconds)
    if args.action == "heartbeat":
        return store.heartbeat(str(args.run_id))
    if args.action == "resume":
        return store.resume(str(args.run_id))
    if args.action == "fail":
        return store.fail(str(args.run_id), reason=args.reason)
    if args.action == "stop":
        return store.stop(str(args.run_id), reason=args.reason)
    if args.action in {"attest", "complete"}:
        return store.complete(str(args.run_id))
    if args.action == "orchestrate":
        commands = json.loads(args.command_json or "[]")
        if not isinstance(commands, list):
            raise SystemExit("--command-json must be a JSON list of command lists")
        return store.orchestrate(str(args.run_id), [list(item) for item in commands])
    return store.health(str(args.run_id))


if __name__ == "__main__":
    raise SystemExit(main())
