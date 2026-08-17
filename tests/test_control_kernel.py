from __future__ import annotations

from pathlib import Path

from project_pipeline.control import BuildSequencer, ProjectControlKernel
from project_pipeline.control.kernel import issue_has_reconciliation_evidence
from project_pipeline.domain.control import EligibilityState, TaskControlFact
from project_pipeline.domain.state import TaskLifecycleState
from project_pipeline.io import read_json, write_json
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
        assert snapshot.scope.requirement_count == 352
        assert not snapshot.scope.findings
        assert snapshot.completion.state.value == "FAILED"
        assert any(
            "ordinary active lanes remain" in reason for reason in snapshot.completion.reasons
        )
        assert snapshot.completion.final_completion_gate_satisfied is False
        assert snapshot.completion.ready_work_items == snapshot.sequence.ready_count


def test_ready_plan_is_read_only_and_versioned(tmp_path: Path) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        before = {item.task_id: item.version for item in store.list_task_states("PROJECT-PIPELINE")}
        plan = kernel.readiness_transition_plan()
        after = {item.task_id: item.version for item in store.list_task_states("PROJECT-PIPELINE")}
        assert plan == ()
        assert before == after


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


def test_targeted_readiness_apply_preserves_other_ready_backlog_items(tmp_path: Path) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        assert kernel.readiness_transition_plan() == ()
        results = kernel.apply_readiness_transitions(
            actor_id="actor:test-control",
            correlation_id="corr:test-control-targeted",
        )
        assert results == ()


def test_targeted_readiness_plan_rejects_unknown_task(tmp_path: Path) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        try:
            kernel.readiness_transition_plan(task_ids=frozenset({"PP-TASK-999999"}))
        except ValueError as error:
            assert "unknown task IDs" in str(error)
        else:
            raise AssertionError("unknown task ID must fail closed")


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


def test_already_implemented_work_requires_reconciliation_not_new_implementation() -> None:
    fact = TaskControlFact(
        task_id="PP-TASK-000001",
        project_id="PROJECT-PIPELINE",
        state=TaskLifecycleState.BACKLOG,
        priority="P1",
        risk="MEDIUM",
        requirement_ids=("REQ-ASSURE-0008",),
        reconciliation_required=True,
    )

    decision = BuildSequencer((fact,)).eligibility(fact)

    assert decision.state is EligibilityState.RECONCILIATION_REQUIRED
    assert not decision.eligible
    assert "batch-reconcile" in decision.reasons[0]


def test_issue_level_proof_is_required_before_reconciliation_routing(tmp_path: Path) -> None:
    artifact = tmp_path / "src" / "feature.py"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("VALUE = 1\n", encoding="utf-8")
    issue = {
        "implementation_state": "PLANNED_ONLY",
        "expected_implementation_artifacts": ["src/feature.py"],
        "acceptance_criteria": [
            {"verification": {"status": "PLANNED", "path": "src/feature.py"}},
        ],
        "required_tests": ["TEST-FEATURE-001"],
        "completion_evidence": [],
    }

    assert not issue_has_reconciliation_evidence(tmp_path, issue)

    issue["implementation_state"] = "IMPLEMENTED"
    issue["acceptance_criteria"][0]["verification"]["status"] = "VERIFIED"
    issue["completion_evidence"] = ["EVID-000001"]
    assert issue_has_reconciliation_evidence(tmp_path, issue)


def test_planned_issue_with_existing_artifacts_and_evidence_routes_to_audit(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "src" / "feature.py"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("VALUE = 1\n", encoding="utf-8")
    issue = {
        "implementation_state": "PLANNED_ONLY",
        "expected_implementation_artifacts": ["src/feature.py"],
        "acceptance_criteria": [
            {"verification": {"status": "PLANNED", "path": "src/feature.py"}},
        ],
        "required_tests": ["TEST-FEATURE-001"],
        "completion_evidence": ["EVID-000001"],
    }

    assert issue_has_reconciliation_evidence(tmp_path, issue)


def test_missing_issue_artifact_cannot_be_hidden_by_complete_requirement_evidence(
    tmp_path: Path,
) -> None:
    issue = {
        "implementation_state": "IMPLEMENTED",
        "expected_implementation_artifacts": ["src/missing.py"],
        "acceptance_criteria": [{"verification": {"status": "VERIFIED", "path": "src/missing.py"}}],
        "required_tests": ["TEST-FEATURE-001"],
        "completion_evidence": ["EVID-000001"],
    }

    assert not issue_has_reconciliation_evidence(tmp_path, issue)


def test_known_mismapped_incomplete_task_remains_implementation_eligible(
    tmp_path: Path,
) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        fact = next(item for item in kernel.task_facts() if item.task_id == "PP-TASK-000168")

        assert not fact.reconciliation_required
        assert (
            BuildSequencer(kernel.task_facts()).eligibility(fact).state
            is not EligibilityState.RECONCILIATION_REQUIRED
        )


def test_issue_with_complete_requirements_but_incomplete_issue_proof_is_quarantined(
    tmp_path: Path,
) -> None:
    audit = read_json(ROOT / "plans/reconciliation/IMPLEMENTED_REQUIREMENT_JIRA_AUDIT.json")
    issue_id = next(
        item["issue_id"]
        for item in audit["issue_findings"]
        if item["issue_id"].startswith("PP-TASK-")
    )
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        fact = next(item for item in kernel.task_facts() if item.task_id == issue_id)

        assert fact.reconciliation_required
        assert (
            BuildSequencer(kernel.task_facts()).eligibility(fact).state
            is EligibilityState.RECONCILIATION_REQUIRED
        )


def test_existing_delivery_footprints_are_not_ranked_as_fresh_implementation(
    tmp_path: Path,
) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        facts = {item.task_id: item for item in kernel.task_facts()}
        sequencer = BuildSequencer(facts.values())

        for task_id in (
            "PP-TASK-000346",
            "PP-TASK-000347",
            "PP-TASK-000348",
            "PP-TASK-000349",
            "PP-TASK-000354",
            "PP-TASK-000356",
        ):
            assert facts[task_id].reconciliation_required
            assert (
                sequencer.eligibility(facts[task_id]).state
                is EligibilityState.RECONCILIATION_REQUIRED
            )


def test_product_repair_pauses_normal_control_selection_but_keeps_runtime_slice(
    tmp_path: Path,
) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        facts = {item.task_id: item for item in kernel.task_facts()}
        sequencer = BuildSequencer(facts.values())

        assert not facts["PP-TASK-000168"].product_scope_allowed
        assert (
            sequencer.eligibility(facts["PP-TASK-000168"]).state
            is EligibilityState.PRODUCT_SCOPE_PAUSED
        )
        assert facts["PP-TASK-000381"].product_scope_allowed


def test_invalid_control_selection_contract_fails_closed_for_all_work(tmp_path: Path) -> None:
    contract_path = ROOT / "config/product_outcome.json"
    original = read_json(contract_path)
    modified = dict(original)
    modified["control_selection"] = {
        "mode": "NORMAL_BACKLOG",
        "allowed_issue_ids": ["PP-TASK-000168"],
        "resume_rule": "invalid",
    }
    write_json(contract_path, modified)
    try:
        with initialized_store(tmp_path / "control.db") as store:
            kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
            facts = kernel.task_facts()
            assert facts
            assert all(not item.product_scope_allowed for item in facts)
    finally:
        write_json(contract_path, original)


def test_completion_projection_flags_ordinary_active_lanes_during_product_audit(
    tmp_path: Path,
) -> None:
    with initialized_store(tmp_path / "control.db") as store:
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        snapshot = kernel.evaluate()
        assert snapshot.completion.state.value == "FAILED"
        assert any(
            "ordinary active lanes remain" in reason for reason in snapshot.completion.reasons
        )
