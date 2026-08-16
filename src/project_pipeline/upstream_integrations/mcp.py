from __future__ import annotations

from dataclasses import dataclass

from project_pipeline.contracts.envelopes import ActionIntent, ApprovalState
from project_pipeline.upstream_integrations.common import UpstreamIntegrationError


@dataclass(frozen=True, slots=True)
class McpServerProfile:
    upstream_id: str
    name: str
    endpoint: str
    transport: str
    auth_mode: str
    secret_reference: str
    authority: str
    writes_default_enabled: bool = False
    evidence_sources: tuple[str, ...] = ()

    def request_headers(self, *, secret_value: str) -> dict[str, str]:
        if not secret_value:
            raise ValueError("secret value must be supplied at runtime")
        return {"Authorization": f"Bearer {secret_value}"}

    def authorize_write(self, intent: ActionIntent | None, *, operation: str) -> bool:
        if intent is None or intent.approval_state is not ApprovalState.APPROVED:
            return False
        return (
            intent.authority == self.authority
            and intent.target == self.endpoint
            and intent.operation == operation
        )


def github_mcp_profile() -> McpServerProfile:
    return McpServerProfile(
        upstream_id="UPSTREAM-041",
        name="github-official-mcp",
        endpoint="https://api.githubcopilot.com/mcp/",
        transport="http",
        auth_mode="oauth_or_pat",
        secret_reference="env:GITHUB_MCP_TOKEN",
        authority="github.steward",
        evidence_sources=("github/github-mcp-server:README.md",),
    )


def atlassian_mcp_profile() -> McpServerProfile:
    return McpServerProfile(
        upstream_id="UPSTREAM-011",
        name="atlassian-rovo-mcp",
        endpoint="https://mcp.atlassian.com/v1/mcp/authv2",
        transport="http",
        auth_mode="oauth2.1_or_api_token",
        secret_reference="env:ATLASSIAN_MCP_TOKEN",
        authority="jira.steward",
        evidence_sources=("atlassian/atlassian-mcp-server:README.md",),
    )


def require_mcp_write(
    profile: McpServerProfile, intent: ActionIntent | None, *, operation: str
) -> None:
    if not profile.authorize_write(intent, operation=operation):
        raise UpstreamIntegrationError("MCP mutation is not authorized by the owning steward")
