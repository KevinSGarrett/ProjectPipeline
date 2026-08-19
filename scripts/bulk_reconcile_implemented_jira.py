"""Current-main Jira implementation reconciliation without historical base-ref reverts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from project_pipeline.assurance.jira_implementation_reconciliation import (
    apply_jira_implementation_reconciliation,
    evaluate_jira_implementation_reconciliation,
)
from project_pipeline.io import write_json


def reconcile(root: Path, *, apply: bool, base_ref: str | None = None) -> dict[str, Any]:
    del base_ref  # Historical revert-to-base behavior is unsafe and is not used.
    ledger = evaluate_jira_implementation_reconciliation(root)
    result = {
        "schema_version": "2.0.0",
        "apply": apply,
        "rule": (
            "Evidence-bound current-main reconciliation only. Historical --base-ref reverts, "
            "paused-lane exclusions, and per-lifecycle branches are not applied."
        ),
        "ledger_count": len(ledger),
        "accepted_count": sum(1 for item in ledger if item.get("accepted")),
        "candidate_issue_ids": [
            item["issue_id"]
            for item in ledger
            if item.get("accepted") and item.get("next_implementation_state") == "IMPLEMENTED"
        ],
        "done_issue_ids": [
            item["issue_id"]
            for item in ledger
            if item.get("accepted") and item.get("next_lifecycle_state") == "DONE"
        ],
        "ledger": ledger,
    }
    if apply:
        applied = apply_jira_implementation_reconciliation(root)
        result.update(applied)
        result["apply"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Ignored. Kept for compatibility; historical revert-to-base is disabled.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    result = reconcile(root, apply=args.apply, base_ref=args.base_ref)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        write_json(output, result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
