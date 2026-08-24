from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.validation import RepositoryValidator  # noqa: E402

report = RepositoryValidator(ROOT).validate()
print(report.render())
raise SystemExit(0 if report.ok else 1)
