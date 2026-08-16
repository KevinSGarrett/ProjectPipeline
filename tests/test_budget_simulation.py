from pathlib import Path

from project_pipeline.budget.simulation import simulate_scenario, supported_scenarios
from project_pipeline.domain.budget import PressureMode


def test_all_budget_simulations_execute_deterministically():
    root = Path.cwd()
    results = [simulate_scenario(root, name) for name in supported_scenarios()]
    assert len({item.simulation_id for item in results}) == len(results)
    assert all(item.scenario in supported_scenarios() for item in results)


def test_unknown_outcome_simulation_holds_reservation():
    result = simulate_scenario(Path.cwd(), "unknown_outcome")
    assert "reservation_held:True" in result.notes


def test_yellow_simulation_prefers_conservation_modes():
    result = simulate_scenario(Path.cwd(), "yellow_conservation")
    assert result.pressure_mode in {PressureMode.YELLOW, PressureMode.ORANGE, PressureMode.RED}
    assert "LOCAL" in result.notes
