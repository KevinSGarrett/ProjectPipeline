from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.line_numbering import generate_line_numbered_plans  # noqa: E402
from project_pipeline.manifest import write_manifest  # noqa: E402
from project_pipeline.repository_map import write_repository_map  # noqa: E402
from project_pipeline.traceability import (  # noqa: E402
    rebuild_traceability_exports,
    write_coverage_artifacts,
)

generate_line_numbered_plans(ROOT)
rebuild_traceability_exports(ROOT)
write_coverage_artifacts(ROOT)
write_repository_map(ROOT)
manifest = write_manifest(ROOT)
print(f"Generated project assets for {manifest['file_count']} files.")
