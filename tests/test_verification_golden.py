from pathlib import Path

from project_pipeline.domain.verification import VerificationResultState
from project_pipeline.verification.golden import definitions, run_all


def test_golden_journey_definitions_are_stable_and_objective():
    values = definitions()
    assert len(values) == 4
    assert len({item.journey_id for item in values}) == 4
    assert all(item.required_observations for item in values)


def test_all_current_golden_journeys_pass(project_root: Path):
    values = run_all(project_root)
    assert len(values) == 4
    assert all(item.state is VerificationResultState.PASS for item in values)


def test_golden_journeys_define_environment_setup_actions_results_cleanup_and_evidence():
    for journey in definitions():
        assert journey.environment
        assert journey.setup_steps
        assert journey.action_steps
        assert journey.expected_results
        assert journey.cleanup_steps
        assert journey.evidence_expectations
