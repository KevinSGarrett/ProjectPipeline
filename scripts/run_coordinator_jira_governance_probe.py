"""Run the coordinator-owned Jira portion of PP-384 without exporting a secret."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.autonomy_runtime.live_qualification import (  # noqa: E402
    _PRIMARY_COORDINATOR_ID,
    create_coordinator_jira_governance_receipt,
)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=path.parent, prefix=f".{path.name}."
    ) as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coordinator-id", default=_PRIMARY_COORDINATOR_ID)
    args = parser.parse_args()
    receipt = create_coordinator_jira_governance_receipt(
        repository_root=args.root.resolve(), coordinator_id=args.coordinator_id
    )
    _write_json_atomic(args.output.resolve(), receipt)
    print(
        json.dumps(
            {
                "written": str(args.output.resolve()),
                "status": receipt["status"],
                "candidate": receipt["candidate"],
                "secret_value_observed": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
