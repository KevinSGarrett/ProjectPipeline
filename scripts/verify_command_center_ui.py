from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.command_center.application_verification import verify_command_center_ui
from project_pipeline.command_center.live_browser import verify_live_command_center
from project_pipeline.verification.browser import find_chromium

chromium = find_chromium()
if chromium is None:
    raise SystemExit("Chromium is unavailable; Command Center browser verification cannot run")
preview = verify_command_center_ui(ROOT, chromium_path=chromium, write_evidence=False)
live = verify_live_command_center(ROOT, chromium_path=chromium, write_evidence=False)
print(
    json.dumps(
        {
            "preview_passed": preview["passed"],
            "live_passed": live["passed"],
            "preview_target": preview["target"],
            "live_target": live["target"],
            "viewports": len(preview["viewports"]),
        },
        sort_keys=True,
    )
)
raise SystemExit(0 if preview["passed"] and live["passed"] else 1)
