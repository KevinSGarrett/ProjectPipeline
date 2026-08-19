from __future__ import annotations

from pathlib import Path

from project_pipeline.command_center.application import RepositoryApplicationProjectionBuilder
from project_pipeline.command_center.models import CommandCenterSnapshot, HealthState
from project_pipeline.control import (
    BuildSequencer,
    ProjectControlKernel,
    assert_cohort_invariants,
    describe_reconciliation_cohorts,
    summarize_control_cohorts,
)
from project_pipeline.domain.control import EligibilityState, ReadinessState
from project_pipeline.persistence import SQLiteStateStore
from project_pipeline.services import CoreStateService

ROOT = Path(__file__).resolve().parents[1]


def test_same_snapshot_control_cohorts_are_labeled_and_invariant(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "control.db", ROOT)
    with store:
        CoreStateService(store, ROOT).initialize_from_repository()
        kernel = ProjectControlKernel(ROOT, store, "PROJECT-PIPELINE")
        facts = kernel.task_facts()
        sequencer = BuildSequencer(facts)
        sequence = sequencer.build_sequence()
        eligibility = tuple(sequencer.eligibility(item) for item in facts)
        readiness = tuple(sequencer.readiness(item) for item in facts)
        snapshot = kernel.evaluate()
        cohorts = snapshot.completion.cohorts
        assert_cohort_invariants(facts, eligibility, readiness, cohorts)
        recomputed = summarize_control_cohorts(facts, eligibility, readiness)
        assert recomputed == cohorts
        assert cohorts.total_work_items == len(facts) == snapshot.completion.total_work_items
        assert (
            cohorts.dependency_ready == sequence.ready_count == snapshot.completion.ready_work_items
        )
        assert cohorts.eligibility_eligible == sum(
            item.state is EligibilityState.ELIGIBLE for item in eligibility
        )
        assert cohorts.dependency_ready == sum(
            item.state is ReadinessState.READY for item in readiness
        )
        sentence = describe_reconciliation_cohorts(cohorts)
        assert "immediately batchable" not in sentence
        assert "structural container" in sentence
        assert any("structural container" in reason for reason in snapshot.completion.reasons) or (
            cohorts.reconciliation_facts == 0
        )
        epic_facts = [
            item
            for item in facts
            if item.issue_type == "EPIC"
            and item.reconciliation_required
            and item.state.value not in {"DONE", "CANCELLED"}
        ]
        assert cohorts.structural_container_facts == len(epic_facts)
        for item in eligibility:
            if item.task_id in {fact.task_id for fact in epic_facts}:
                assert item.state is EligibilityState.POLICY_DENIED
                assert "structural work container" in " ".join(item.reasons)
        cc_snapshot = CommandCenterSnapshot(
            snapshot_id="cc-cohort-invariant",
            project_id="PROJECT-PIPELINE",
            operating_mode="local",
            overall_health=HealthState.HEALTHY,
            health=(),
            context_summary={"control_cohorts": cohorts.model_dump(mode="json")},
            fingerprint="a" * 64,
        )
        projection = RepositoryApplicationProjectionBuilder(ROOT).build(cc_snapshot)
        assert projection.context_detail["control_cohorts"] == cohorts.model_dump(mode="json")
        assert projection.context_detail["reconciliation_is_immediately_batchable"] is False
        assert "immediately batchable" not in str(
            projection.context_detail["reconciliation_sentence"]
        )
        assert projection.context_detail["reconciliation_sentence"] == sentence
