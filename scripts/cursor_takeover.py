from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_pipeline.cursor_takeover import (
    build_cursor_contract,
    build_cursor_cycle_plan,
    initialize_supervisor_state,
    record_supervisor_cycle,
    takeover_prompt,
    validate_cursor_takeover,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Governed Cursor takeover and bounded-cycle planner"
    )
    parser.add_argument(
        "command",
        choices=("validate", "plan", "contract", "prompt", "state-init", "state-record"),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--database", type=Path)
    parser.add_argument("--project-id", default="PROJECT-PIPELINE")
    parser.add_argument("--objective-progress-units", type=int, default=0)
    parser.add_argument("--completion-gate", default="NOT_COMPLETE")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "validate":
        report = validate_cursor_takeover(root)
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 0 if report.configuration_ready else 1
    if args.command == "prompt":
        print(takeover_prompt())
        return 0
    if args.command == "state-init":
        state = initialize_supervisor_state(root)
        print(json.dumps(state.model_dump(mode="json"), indent=2))
        return 0
    if args.command == "state-record":
        state = record_supervisor_cycle(
            root,
            objective_progress_units=args.objective_progress_units,
            completion_gate=args.completion_gate,
        )
        print(json.dumps(state.model_dump(mode="json"), indent=2))
        return 0 if state.status == "READY" else 2
    if args.database is None:
        parser.error("--database is required for plan and contract")
    plan = build_cursor_cycle_plan(root, args.database, args.project_id)
    if args.command == "plan":
        print(json.dumps(plan.model_dump(mode="json"), indent=2))
        return 0 if plan.selected_task_id else 2
    contract = build_cursor_contract(root, plan)
    print(json.dumps(contract.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
