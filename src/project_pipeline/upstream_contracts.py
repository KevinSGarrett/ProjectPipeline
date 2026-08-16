from __future__ import annotations

import json
from importlib import resources
from typing import Any


def _load_json(name: str) -> dict[str, Any]:
    package = resources.files("project_pipeline.upstream_data")
    return json.loads(package.joinpath(name).read_text(encoding="utf-8"))


def pydantic_ai_provider_compatibility() -> dict[str, Any]:
    """Return the reviewed Pydantic AI provider-compatibility contract."""
    return _load_json("pydantic_ai_provider_compatibility.json")


def docker_mcp_gateway_security_defaults() -> dict[str, Any]:
    """Return the reviewed Docker MCP Gateway security defaults."""
    return _load_json("docker_mcp_gateway_security_defaults.json")
