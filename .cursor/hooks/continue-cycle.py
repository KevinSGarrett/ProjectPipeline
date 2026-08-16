from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("status") != "completed":
        print("{}")
        return 0
    state_path = Path(".local/state/cursor/supervisor-state.json")
    if not state_path.exists():
        print("{}")
        return 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("stop_requested") or state.get("completion_gate") == "COMPLETE":
        print("{}")
        return 0
    if int(state.get("consecutive_progressless_cycles", 0)) >= 2:
        print("{}")
        return 0
    print(
        json.dumps(
            {
                "followup_message": (
                    "Continue the bounded ProjectPipeline cycle from durable state. "
                    "Re-run takeover validation and Control selection; do not create "
                    "lifecycle-only work or bypass any external-write gate."
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
