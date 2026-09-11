"""Bounded isolated Control graph for Cycle 21 validation jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.task_execution_specs import (
    VALIDATION_ALPHA_TASK,
    VALIDATION_BETA_TASK,
)
from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.domain.state import TaskLifecycleState, TaskStateRecord
from project_pipeline.overlay import control_input_root
from project_pipeline.persistence import SQLiteStateStore


def _issue(
    local_id: str, *, state: str, dependencies: tuple[str, ...], title: str
) -> dict[str, Any]:
    return {
        "local_id": local_id,
        "issue_type": "TASK" if local_id.startswith("PP-TASK-") else "STORY",
        "title": title,
        "parent": "PP-STORY-000396",
        "objective": title,
        "rationale": "Cycle-owned isolated validation graph; not a live PP ticket.",
        "description": "Disposable Control-selected validation job for Cycle 21 mixed-hour proof.",
        "scope": ["Isolated Control selection, native tests, and continuation."],
        "exclusions": ["Not a production PP inventory item and not a criterion stamp."],
        "requirement_ids": [],
        "source_references": [],
        "plan_references": [],
        "dependencies": list(dependencies),
        "blockers": [],
        "relationships": [{"type": "DEPENDS_ON", "target": item} for item in dependencies],
        "upstream_dependencies": [],
        "expected_implementation_artifacts": [
            "src/project_pipeline/autonomy_runtime/task_execution_specs.py"
        ],
        "expected_file_locations": ["tests/fixtures"],
        "acceptance_criteria": [],
        "definition_of_done": ["Task-specific native tests pass."],
        "required_tests": [],
        "evidence_required": [],
        "risk_classification": "LOW",
        "security_impact": "None; isolated validation graph.",
        "observability_impact": "Control readiness and fleet-loop continuation.",
        "rollback_recovery_consideration": "Delete cycle-owned isolated job files.",
        "owner_required_capability": "fleet_validation",
        "labels": ["cycle21-isolated-validation"],
        "state": state,
        "implementation_state": "PARTIALLY_IMPLEMENTED",
        "completion_evidence": [],
    }


def write_isolated_issues(root: Path) -> list[Path]:
    input_root = control_input_root(root)
    folder = input_root / "jira" / "tasks"
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    payloads = (
        _issue(
            VALIDATION_ALPHA_TASK,
            state="READY",
            dependencies=(),
            title="Isolated validation job alpha with distinct tests",
        ),
        _issue(
            VALIDATION_BETA_TASK,
            state="BACKLOG",
            dependencies=(VALIDATION_ALPHA_TASK,),
            title="Isolated validation job beta depending on alpha",
        ),
    )
    for payload in payloads:
        path = folder / f"{payload['local_id']}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


def ensure_isolated_validation_graph(root: Path, database: Path) -> dict[str, Any]:
    """Install the isolated 992→993 graph through production APIs when the root is a project."""

    root = root.resolve()
    if not (root / "config" / "project.json").is_file():
        return {"ok": False, "reason": "not_a_project_root"}
    write_isolated_issues(root)
    project_id = load_runtime_configuration(root).settings.project_id
    tasks = (
        TaskStateRecord(
            task_id=VALIDATION_ALPHA_TASK,
            project_id=project_id,
            state=TaskLifecycleState.READY,
            priority="P1",
        ),
        TaskStateRecord(
            task_id=VALIDATION_BETA_TASK,
            project_id=project_id,
            state=TaskLifecycleState.BACKLOG,
            priority="P1",
            dependency_ids=(VALIDATION_ALPHA_TASK,),
        ),
    )
    with SQLiteStateStore(database, root) as store:
        store.initialize()
        if store.get_project_manifest(project_id) is None:
            return {"ok": False, "reason": "project_not_initialized", "project_id": project_id}
        store.put_task_states(tasks)
        return {
            "ok": True,
            "project_id": project_id,
            "task_ids": [item.task_id for item in tasks],
        }


def mark_verified_predecessor(root: Path, database: Path, task_id: str) -> None:
    root = root.resolve()
    project_id = load_runtime_configuration(root).settings.project_id
    with SQLiteStateStore(database, root) as store:
        store.initialize()
        current = store.get_task_state(task_id)
        if current is None:
            return
        store.put_task_states(
            (
                current.model_copy(
                    update={"state": TaskLifecycleState.DONE, "version": current.version + 1}
                ),
            )
        )
        _ = project_id
