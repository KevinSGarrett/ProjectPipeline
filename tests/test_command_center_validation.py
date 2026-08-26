from project_pipeline.command_center.simulation import run_command_center_simulations


def test_command_center_simulations_pass():
    assert all(run_command_center_simulations().values())
