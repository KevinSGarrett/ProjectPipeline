from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_pipeline.jira_steward.alignment import validate_jira_operational_alignment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed on Jira source/database/projection/readback disagreement."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    report = validate_jira_operational_alignment(args.root, args.database)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
