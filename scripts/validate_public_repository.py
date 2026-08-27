from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate ProjectPipeline's professional public repository surface."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    sys.path.insert(0, str(root / "src"))

    from project_pipeline.validation.public_repository import (
        validate_public_repository_surface,
    )

    errors = validate_public_repository_surface(root)
    if errors:
        print("Public repository validation: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Public repository validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
