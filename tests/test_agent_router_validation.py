from project_pipeline.agent_router import load_agent_registry, validate_agent_router_foundation


def test_agent_router_foundation_is_registered_and_valid():
    root = __import__("pathlib").Path(__file__).parents[1]
    registry = load_agent_registry(root)
    assert registry.providers and registry.capabilities
    assert validate_agent_router_foundation(root) == []


def test_cursor_provider_is_registered_and_live_qualified():
    root = __import__("pathlib").Path(__file__).parents[1]
    registry = load_agent_registry(root)
    provider = next(
        item for item in registry.providers if item.provider_id == "provider:cursor-cli"
    )
    assert provider.enabled is True
    models = [item for item in registry.models if item.provider_id == provider.provider_id]
    assert models and all(item.qualification.value == "QUALIFIED" for item in models)
