"""Create verified machine-local Cursor attestation records for an isolated worker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_pipeline.lifecycle.attestation_recovery import (
    bootstrap_machine_local_attestation_records,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--durable-dir", type=Path)
    parser.add_argument("--verification-dir", type=Path)
    args = parser.parse_args()
    result = bootstrap_machine_local_attestation_records(
        repository_root=args.repository_root,
        durable_dir=args.durable_dir,
        verification_dir=args.verification_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
