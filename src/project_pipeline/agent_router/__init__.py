from project_pipeline.agent_router.adapters import (
    AnthropicMessagesAdapter,
    GeminiGenerateContentAdapter,
    LiteLLMProxyAdapter,
    LocalProcessProviderAdapter,
    MockProviderAdapter,
    MockToolAdapter,
    OpenAIResponsesAdapter,
    ProviderAdapter,
    ProviderAdapterError,
    ToolAdapter,
)
from project_pipeline.agent_router.circuit import (
    normalize_circuit,
    record_failure,
    record_probe,
    record_success,
)
from project_pipeline.agent_router.docker_mcp_gateway import DockerMCPGatewayAdapter
from project_pipeline.agent_router.persistence import AgentRouterStore
from project_pipeline.agent_router.pydantic_ai_adapter import PydanticAIProviderAdapter
from project_pipeline.agent_router.qualification import (
    REQUIRED_ADAPTER_CHECKS,
    qualification_report,
)
from project_pipeline.agent_router.registry import (
    build_registry,
    execution_targets,
    load_agent_registry,
)
from project_pipeline.agent_router.router import AgentRouter
from project_pipeline.agent_router.service import AgentRouterService, AgentRoutingError
from project_pipeline.agent_router.simulation import simulate_provider_failover
from project_pipeline.agent_router.validation import validate_agent_router_foundation

__all__ = [
    "REQUIRED_ADAPTER_CHECKS",
    "AgentRouter",
    "AgentRouterService",
    "AgentRouterStore",
    "AgentRoutingError",
    "AnthropicMessagesAdapter",
    "DockerMCPGatewayAdapter",
    "GeminiGenerateContentAdapter",
    "LiteLLMProxyAdapter",
    "LocalProcessProviderAdapter",
    "MockProviderAdapter",
    "MockToolAdapter",
    "OpenAIResponsesAdapter",
    "ProviderAdapter",
    "ProviderAdapterError",
    "PydanticAIProviderAdapter",
    "ToolAdapter",
    "build_registry",
    "execution_targets",
    "load_agent_registry",
    "normalize_circuit",
    "qualification_report",
    "record_failure",
    "record_probe",
    "record_success",
    "simulate_provider_failover",
    "validate_agent_router_foundation",
]
