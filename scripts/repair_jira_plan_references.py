from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from project_pipeline.io import read_json, write_json

_CONTEXT_REPAIRS = {
    "PP-TASK-000168",
    "PP-EPIC-000036",
    *(f"PP-STORY-{value:06d}" for value in range(138, 144)),
    *(f"PP-TASK-{value:06d}" for value in range(380, 386)),
}


def _issue_paths(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for directory in ("epics", "stories", "tasks", "subtasks", "bugs", "spikes")
        for path in sorted((root / "jira" / directory).glob("PP-*.json"))
    )


def repair(root: Path) -> dict[str, int]:
    index = read_json(root / "plans/_indexes/plan_section_index.json")
    reference_repairs = 0
    context_repairs = 0
    for path in _issue_paths(root):
        issue = read_json(path)
        references: list[dict[str, Any]] = []
        for reference in issue.get("plan_references", []):
            section_id = str(reference.get("section_id", ""))
            canonical = index.get(section_id)
            if canonical is None:
                raise ValueError(f"unknown plan section in {issue['local_id']}: {section_id}")
            references.append({"section_id": section_id, **canonical})
        if references != issue.get("plan_references", []):
            issue["plan_references"] = references
            write_json(path, issue)
            reference_repairs += 1
        issue_id = str(issue["local_id"])
        context_path = root / "jira/source_context" / f"{issue_id}.md"
        if context_path.exists() and issue_id not in _CONTEXT_REPAIRS:
            continue
        plan_values = ", ".join(
            f"`{item['line_reference']}`" for item in issue.get("plan_references", [])
        ) or "None."
        requirement_values = ", ".join(
            f"`{item}`" for item in issue.get("requirement_ids", [])
        ) or "None."
        source_values = "\n".join(
            f"- `{item}`" for item in issue.get("source_references", [])
        ) or "None."
        context_path.write_text(
            "\n".join(
                [
                    f"# {issue_id} — Source Context",
                    "",
                    f"- Title: {issue['title']}",
                    f"- Plan: {plan_values}",
                    f"- Requirements: {requirement_values}",
                    "",
                    "## Canonical source references",
                    "",
                    source_values,
                    "",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )
        context_repairs += 1
    return {
        "plan_reference_repairs": reference_repairs,
        "source_context_repairs": context_repairs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = repair(args.root.resolve())
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
