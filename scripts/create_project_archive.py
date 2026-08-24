from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_pipeline.archive import create_archive, verify_archive  # noqa: E402
from project_pipeline.validation.repository import RepositoryValidator  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
validation = RepositoryValidator(ROOT).validate()
if validation.errors or validation.warnings:
    print(validation.as_dict())
    raise SystemExit(2)
archive = create_archive(ROOT, args.output)
report = verify_archive(archive, ROOT.name)
print(report.as_dict())
raise SystemExit(0 if report.ok else 1)
