from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage hashed desktop build artifacts")
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    compare_dir = args.output_dir / "compare"
    identity_dir = args.output_dir / "identity"
    compare_dir.mkdir(parents=True, exist_ok=True)
    identity_dir.mkdir(parents=True, exist_ok=True)
    compare_files = list(args.release_dir.glob("*.exe"))
    identity_files = [
        *list((args.release_dir / "bundle" / "msi").glob("*.msi")),
        *list((args.release_dir / "bundle" / "nsis").glob("*.exe")),
    ]
    manifest: list[dict[str, str | int]] = []
    for path in compare_files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        shutil.copy2(path, compare_dir / path.name)
        manifest.append(
            {
                "name": path.name,
                "role": "compare",
                "sha256": digest,
                "bytes": path.stat().st_size,
            }
        )
    for path in identity_files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        shutil.copy2(path, identity_dir / path.name)
        manifest.append(
            {
                "name": path.name,
                "role": "identity",
                "sha256": digest,
                "bytes": path.stat().st_size,
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "hashes.json").write_text(
        json.dumps(
            {"lane": args.lane, "head": args.head, "files": manifest},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0 if compare_files else 1


if __name__ == "__main__":
    raise SystemExit(main())
