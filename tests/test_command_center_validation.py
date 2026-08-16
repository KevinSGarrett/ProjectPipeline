from project_pipeline.command_center.simulation import run_command_center_simulations
from project_pipeline.command_center.validation import validate_command_center_foundation


def test_command_center_simulations_pass():
    assert all(run_command_center_simulations().values())


def test_command_center_foundation_validator_clean(project_root):
    assert validate_command_center_foundation(project_root) == []
