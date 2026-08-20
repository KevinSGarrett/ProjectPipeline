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
    release_dir = args.release_dir
    files = [
        *release_dir.glob("*.exe"),
        *list((release_dir / "bundle" / "msi").glob("*.msi")),
        *list((release_dir / "bundle" / "nsis").glob("*.exe")),
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str | int]] = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        shutil.copy2(path, args.output_dir / path.name)
        manifest.append({"name": path.name, "sha256": digest, "bytes": path.stat().st_size})
    (args.output_dir / "hashes.json").write_text(
        json.dumps(
            {"lane": args.lane, "head": args.head, "files": manifest},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0 if files else 1


if __name__ == "__main__":
    raise SystemExit(main())
