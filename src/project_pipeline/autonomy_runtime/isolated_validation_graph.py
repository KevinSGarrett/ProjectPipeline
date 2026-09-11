"""Bounded isolated Control graph for Cycle 21 validation jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.autonomy_runtime.task_execution_specs import (
    VALIDATION_ALPHA_TASK,
    VALIDATION_BETA_TASK,
)
from project_pipeline.autonomy_runtime.worker_allowlist import CYCLE_OWNED_VALIDATION_JOBS
from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.control.kernel import ProjectControlKernel
from project_pipeline.domain.state import TaskLifecycleState, TaskStateRecord
from project_pipeline.persistence import SQLiteStateStore

_TO_DONE: dict[TaskLifecycleState, TaskLifecycleState] = {
    TaskLifecycleState.BACKLOG: TaskLifecycleState.READY,
    TaskLifecycleState.READY: TaskLifecycleState.CLAIMED,
    TaskLifecycleState.CLAIMED: TaskLifecycleState.IN_PROGRESS,
    TaskLifecycleState.IN_PROGRESS: TaskLifecycleState.IN_REVIEW,
    TaskLifecycleState.IN_REVIEW: TaskLifecycleState.VALIDATING,
    TaskLifecycleState.VALIDATING: TaskLifecycleState.DONE,
    TaskLifecycleState.FAILED: TaskLifecycleState.IN_PROGRESS,
}


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
    """Persist verified predecessor DONE through the canonical task-transition API."""

    root = root.resolve()
    with SQLiteStateStore(database, root) as store:
        store.initialize()
        current = store.get_task_state(task_id)
        if current is None:
            return
        actor_id = "actor:cycle21-isolated-validation"
        correlation_id = f"corr:verified-predecessor:{task_id}"
        while current.state is not TaskLifecycleState.DONE:
            next_state = _TO_DONE.get(current.state)
            if next_state is None:
                return
            current = store.transition_task(
                task_id=task_id,
                next_state=next_state,
                expected_version=current.version,
                reason="verified isolated predecessor accepted",
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
        ProjectControlKernel(root, store, current.project_id).apply_readiness_transitions(
            actor_id=actor_id,
            correlation_id=correlation_id,
            task_ids=frozenset(CYCLE_OWNED_VALIDATION_JOBS),
        )
