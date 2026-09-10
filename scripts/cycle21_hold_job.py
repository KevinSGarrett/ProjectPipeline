"""Bounded hold job used for isolated worker-process loss, not useful work."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def run(*, job_id: str, seconds: int, output: Path) -> dict[str, object]:
    payload: dict[str, object] = {
        "job_id": job_id,
        "kind": "cycle21_hold",
        "pid": os.getpid(),
        "seconds": int(seconds),
    }
    print(json.dumps(payload, sort_keys=True), flush=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    time.sleep(max(1, int(seconds)))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(prog="cycle21-hold-job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("hold_artifact.json"))
    args = parser.parse_args()
    run(job_id=args.job_id, seconds=args.seconds, output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
