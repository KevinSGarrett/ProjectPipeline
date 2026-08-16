from pathlib import Path

import pytest

from project_pipeline.verification.simulation import simulate_scenario, supported_scenarios


@pytest.mark.parametrize("scenario", supported_scenarios())
def test_verification_simulations_pass(project_root: Path, scenario: str):
    result = simulate_scenario(project_root, scenario)
    assert result["passed"] is True
