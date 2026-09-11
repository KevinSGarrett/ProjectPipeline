"""Bounded isolated Control graph for Cycle 21 validation jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.task_execution_specs import (
    VALIDATION_ALPHA_TASK,
    VALIDATION_BETA_TASK,
)
from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.domain.state import TaskLifecycleState, TaskStateRecord
from project_pipeline.persistence import SQLiteStateStore


def ensure_isolated_validation_graph(root: Path, database: Path) -> dict[str, Any]:
    """Install the isolated 992→993 graph through production task-state APIs."""

    root = root.resolve()
    if not (root / "config" / "project.json").is_file():
        return {"ok": False, "reason": "not_a_project_root"}
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
