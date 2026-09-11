"""Immutable per-task native execution specs. No default smoke fixture."""

from __future__ import annotations

from typing import Any

NATIVE_PASS_FIXTURE = "tests/fixtures/cycle21_native_pass.py"
SELECTED_ALPHA = "tests/fixtures/cycle21_selected_alpha.py"
SELECTED_BETA = "tests/fixtures/cycle21_selected_beta.py"

# Cycle-owned isolated validation graph (not production PP inventory).
VALIDATION_ALPHA_TASK = "PP-TASK-000992"
VALIDATION_BETA_TASK = "PP-TASK-000993"
VALIDATION_BLOCKED_LANE = "PP-STORY-000139"

SPECS: dict[str, dict[str, Any]] = {
    VALIDATION_ALPHA_TASK: {
        "required_tests": (SELECTED_ALPHA,),
        "implementation_paths": ("src/project_pipeline/autonomy_runtime/context_validation.py",),
    },
    VALIDATION_BETA_TASK: {
        "required_tests": (SELECTED_BETA,),
        "implementation_paths": ("src/project_pipeline/autonomy_runtime/fleet_loop.py",),
        "depends_on": (VALIDATION_ALPHA_TASK,),
    },
}


def required_tests(task_id: str) -> tuple[str, ...]:
    spec = SPECS.get(task_id)
    if spec is None:
        raise ValueError(f"no_execution_spec:{task_id}")
    tests = tuple(str(item) for item in (spec.get("required_tests") or ()) if str(item).strip())
    if not tests:
        raise ValueError(f"no_required_tests:{task_id}")
    if tests == (NATIVE_PASS_FIXTURE,):
        raise ValueError(f"native_pass_not_a_task_spec:{task_id}")
    return tests


def implementation_paths(task_id: str) -> tuple[str, ...]:
    spec = SPECS.get(task_id) or {}
    return tuple(str(item) for item in (spec.get("implementation_paths") or ()))
