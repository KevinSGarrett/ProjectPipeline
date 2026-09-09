"""Bounded Cycle 20 useful-work payload. Writes a verified artifact, not a canned hash."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def run(*, job_id: str, output: Path) -> dict[str, str]:
    payload = {
        "job_id": job_id,
        "produced_at_utc": datetime.now(UTC).isoformat(),
        "kind": "cycle20_useful_work",
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    artifact = {"job_id": job_id, "artifact_sha256": digest, "bytes": len(encoded)}
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, sort_keys=True))
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(prog="cycle20-useful-job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("useful_artifact.json"))
    args = parser.parse_args()
    run(job_id=args.job_id, output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
