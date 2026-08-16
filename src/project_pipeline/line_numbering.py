from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, write_json

SECTION_PATTERN = re.compile(r"^##\s+([A-Z0-9-]+:SEC-[0-9]{2})\b")


def generate_line_numbered_plans(root: Path) -> dict[str, Any]:
    catalog = read_json(root / "plans" / "PLAN_CATALOG.json")
    destination = root / "plans" / "_line_numbered"
    destination.mkdir(parents=True, exist_ok=True)
    section_index: dict[str, Any] = {}
    for plan in catalog["plans"]:
        source = root / plan["path"]
        lines = source.read_text(encoding="utf-8").splitlines()
        rendered = [f"L{number:06d} | {line}" for number, line in enumerate(lines, 1)]
        output = destination / f"{source.stem}.lines.txt"
        output.write_text("\n".join(rendered) + "\n", encoding="utf-8", newline="\n")
        starts: list[tuple[str, int]] = []
        for number, line in enumerate(lines, 1):
            match = SECTION_PATTERN.match(line)
            if match:
                starts.append((match.group(1), number))
        for index, (section_id, start) in enumerate(starts):
            end = starts[index + 1][1] - 1 if index + 1 < len(starts) else len(lines)
            section_index[section_id] = {
                "plan_id": plan["plan_id"],
                "authoritative_path": plan["path"],
                "line_numbered_path": output.relative_to(root).as_posix(),
                "line_reference": f"{section_id}:L{start:06d}-L{end:06d}",
                "start_line": start,
                "end_line": end,
            }
    write_json(root / "plans" / "_indexes" / "plan_section_index.json", section_index)
    return section_index
