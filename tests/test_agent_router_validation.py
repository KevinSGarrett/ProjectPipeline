from project_pipeline.agent_router import load_agent_registry, validate_agent_router_foundation


def test_agent_router_foundation_is_registered_and_valid():
    root = __import__("pathlib").Path(__file__).parents[1]
    registry = load_agent_registry(root)
    assert registry.providers and registry.capabilities
    assert validate_agent_router_foundation(root) == []
