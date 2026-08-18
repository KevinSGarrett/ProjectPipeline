from __future__ import annotations

from pathlib import Path

_RETIRED_TOKENS = (
    "HUMAN" + "_REQUIRED",
    "Human" + "RequiredIncident",
    "exact_" + "human_action",
    "requires_" + "human_approval",
    '"human_' + 'required"',
    '"human_' + 'required_steps"',
)
_ACTIVE_GLOBS = (
    "src/**/*.py",
    "schemas/*.json",
    "config/**/*.json",
    "plans/**/*.md",
    "plans/_traceability/requirements.jsonl",
    "jira/epics/*.json",
    "jira/stories/*.json",
    "jira/tasks/*.json",
    "jira/subtasks/*.json",
    "docs/product/*.md",
    "runbooks/**/*.md",
    "evidence/autonomy_runtime/live_qualification/live_qualification_latest.json",
)
_EXCLUDED_PARTS = frozenset({"00_source", "_line_numbered", "reconciliation"})
_LEGACY_STORAGE_ALLOWLIST = {
    Path("src/project_pipeline/jira_steward/persistence.py"): {
        "requires_" + "human_approval"
    }
}


def validate_autonomous_external_preconditions(root: Path) -> list[str]:
    """Reject retired human-work state from current executable/project truth.

    Historical source captures and immutable evidence are intentionally outside
    this gate. Runtime migration code constructs the retired value from parts so
    old databases can be normalized without making it an emit-capable constant.
    """
    errors: list[str] = []
    checked: set[Path] = set()
    for pattern in _ACTIVE_GLOBS:
        for path in root.glob(pattern):
            if path in checked or not path.is_file():
                continue
            checked.add(path)
            relative = path.relative_to(root)
            if any(part in _EXCLUDED_PARTS for part in relative.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            allowed = _LEGACY_STORAGE_ALLOWLIST.get(relative, set())
            for token in _RETIRED_TOKENS:
                if token in text and token not in allowed:
                    errors.append(
                        "retired human-work API appears in active project truth: "
                        f"{relative.as_posix()}"
                    )
                    break
    return sorted(errors)
