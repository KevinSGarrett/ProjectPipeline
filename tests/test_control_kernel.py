from __future__ import annotations

from pathlib import Path

from project_pipeline.control import ProjectControlKernel
from project_pipeline.jira import load_issues
from project_pipeline.persistence import SQLiteStateStore
from project_pipeline.services import CoreStateService

ROOT = Path(__file__).resolve().parents[1]


def initialized_store(path: Path) -> SQLiteStateStore:
    store = SQLiteStateStore(path, ROOT)
    store.__enter__()
    CoreStateService(store, ROOT).initialize_from_repository()
    return store


def test_repository_control_evaluation_is_consistent(tmp_path: Path) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        snapshot = kernel.evaluate()
        assert snapshot.sequence.task_count == len(load_issues(ROOT))
        assert snapshot.scope.requirement_count == 351
        assert not snapshot.scope.findings
        assert snapshot.completion.state.value == "INCOMPLETE"
        assert snapshot.completion.final_completion_gate_satisfied is False
        assert snapshot.completion.ready_work_items == snapshot.sequence.ready_count


def test_ready_plan_is_read_only_and_versioned(tmp_path: Path) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        before = {item.task_id: item.version for item in store.list_task_states("PROJECT-PIPELINE")}
        plan = kernel.readiness_transition_plan()
        after = {item.task_id: item.version for item in store.list_task_states("PROJECT-PIPELINE")}
        assert plan
        assert before == after
        assert all(item["previous_state"] == "BACKLOG" for item in plan)
        assert all(item["next_state"] == "READY" for item in plan)


def test_apply_readiness_transitions_uses_optimistic_state_api(tmp_path: Path) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        plan = kernel.readiness_transition_plan()
        results = kernel.apply_readiness_transitions(
            actor_id="actor:test-control", correlation_id="corr:test-control"
        )
        assert len(results) == len(plan)
        assert all(item["state"] == "READY" for item in results)
        assert not kernel.readiness_transition_plan()


def test_completion_recomputation_does_not_confuse_done_count_with_project_completion(
    tmp_path: Path,
) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        snapshot = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE").evaluate()
        expected_completed = sum(issue["state"] == "DONE" for issue in load_issues(ROOT))
        assert snapshot.completion.completed_work_items == expected_completed
        assert snapshot.completion.completed_work_items < snapshot.completion.total_work_items
        assert (
            snapshot.completion.implemented_or_external_blocked_requirements
            < snapshot.completion.accepted_requirements
        )
        assert not snapshot.completion.verification_eligible


def test_repeated_unchanged_evaluation_has_same_semantic_snapshot_id(tmp_path: Path) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        first = kernel.evaluate()
        second = kernel.evaluate()
        assert first.snapshot_id == second.snapshot_id
        assert first.snapshot_fingerprint == second.snapshot_fingerprint
        assert first.sequence.sequence_id == second.sequence.sequence_id
