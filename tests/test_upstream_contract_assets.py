from __future__ import annotations

from project_pipeline.upstream_contracts import (
    docker_mcp_gateway_security_defaults,
    pydantic_ai_provider_compatibility,
)


def test_pydantic_ai_provider_contract_is_loaded_from_governed_upstream_asset() -> None:
    data = pydantic_ai_provider_compatibility()
    assert data["upstream_id"] == "UPSTREAM-086"
    assert "litellm" in data["openai_chat_compatible_providers"]
    assert data["license"] == "MIT"


def test_docker_mcp_gateway_contract_preserves_secure_reviewed_defaults() -> None:
    data = docker_mcp_gateway_security_defaults()
    assert data["upstream_id"] == "UPSTREAM-029"
    assert data["secure_defaults"]["block_secrets"] is True
    assert data["secure_defaults"]["verify_signatures"] is True
