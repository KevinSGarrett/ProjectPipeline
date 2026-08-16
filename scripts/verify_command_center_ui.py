from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.command_center.application_verification import verify_command_center_ui
from project_pipeline.verification.browser import find_chromium

chromium = find_chromium(("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"))
if chromium is None:
    raise SystemExit("Chromium is unavailable; Command Center browser verification cannot run")
result = verify_command_center_ui(ROOT, chromium_path=chromium)
print(json.dumps({"passed": result["passed"], "target": result["target"], "viewports": len(result["viewports"])}, sort_keys=True))
raise SystemExit(0 if result["passed"] else 1)
