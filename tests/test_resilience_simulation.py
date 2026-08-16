from project_pipeline.resilience.simulation import simulate_scenario, supported_scenarios


def test_all_resilience_scenarios_preserve_authority(project_root):
    for name in supported_scenarios():
        result = simulate_scenario(project_root, name)
        assert result["passed"], name
        assert result["deterministic_authority_preserved"]
        assert not result["external_mutation_performed"]
