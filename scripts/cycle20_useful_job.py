"""Compatibility entry for deployed job scripts. Native tests are required."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cycle21_validation_job import main, run  # noqa: E402

__all__ = ["main", "run"]


if __name__ == "__main__":
    raise SystemExit(main())
