from project_pipeline.orchestration.simulation import simulate_scenario, supported_scenarios


def test_all_orchestration_simulations_pass(project_root):
    results = [simulate_scenario(project_root, name) for name in supported_scenarios()]
    assert {item.scenario for item in results} == set(supported_scenarios())
    assert all(item.passed for item in results)
    assert {item.final_state for item in results} == {
        "SUCCEEDED",
        "RUNNING",
        "RETRY_SCHEDULED",
        "RECOVERY_REQUIRED",
    }
