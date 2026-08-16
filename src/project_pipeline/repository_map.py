from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.io import iter_repository_files, sha256_file, write_json

MAP_EXCLUSIONS = frozenset(
    {"docs/generated/REPOSITORY_MAP.json", "docs/generated/REPOSITORY_MAP.md"}
)


def build_repository_map(root: Path) -> dict[str, Any]:
    root = root.resolve()
    entries: list[dict[str, Any]] = []
    by_top_level: Counter[str] = Counter()
    by_extension: Counter[str] = Counter()
    semantic_index: dict[str, list[str]] = defaultdict(list)
    for path in iter_repository_files(root, excluded_relative_paths=MAP_EXCLUSIONS):
        relative = path.relative_to(root).as_posix()
        parts = Path(relative).parts
        top = parts[0] if len(parts) > 1 else "_root"
        extension = path.suffix.lower() or "[none]"
        by_top_level[top] += 1
        by_extension[extension] += 1
        if top in {"plans", "jira", "adr", "schemas", "contracts", "provenance", "evidence"}:
            semantic_index[top].append(relative)
        entries.append(
            {
                "path": relative,
                "top_level": top,
                "extension": extension,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schema_version": "1.0.0",
        "project_id": "PROJECT-PIPELINE",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "file_count": len(entries),
        "by_top_level": dict(sorted(by_top_level.items())),
        "by_extension": dict(sorted(by_extension.items())),
        "semantic_index": {key: sorted(value) for key, value in sorted(semantic_index.items())},
        "files": entries,
    }


def write_repository_map(root: Path) -> dict[str, Any]:
    result = build_repository_map(root)
    destination = root / "docs" / "generated"
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "REPOSITORY_MAP.json", result)
    lines = [
        "# Generated Repository Map",
        "",
        f"- Files: `{result['file_count']}`",
        f"- Generated: `{result['generated_at_utc']}`",
        "",
        "## Top-level counts",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in result["by_top_level"].items())
    lines.extend(["", "## Semantic indexes", ""])
    for key, paths in result["semantic_index"].items():
        lines.append(f"### {key}")
        lines.append("")
        lines.extend(f"- `{path}`" for path in paths)
        lines.append("")
    (destination / "REPOSITORY_MAP.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n"
    )
    return result
