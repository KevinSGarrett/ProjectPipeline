# UPSTREAM-052 — IBM MCP Context Forge Context Architecture Adoption

- Repository: `IBM/mcp-context-forge`
- Inspected revision: `6004d236479c12ed2571d9bf9dc5cc20bf3aead7`
- License: Apache-2.0
- Decision: retain `MINE_ARCHITECTURE`; Docker MCP Gateway remains the initial Tool Gateway.

## Adopted architecture lessons

Context Forge's separation of gateway configuration, resource services, prompt services, plugin boundaries and acceptance testing reinforces a useful Project Pipeline boundary: external tools/resources/prompts are federated **behind** a governed gateway and remain distinct from deterministic project authority. The Context subsystem therefore treats external resources as candidates with explicit trust/egress classification and never promotes gateway-returned text to governing instructions automatically.

This is an architecture-pattern adoption, not a claim that Context Forge is installed or live-qualified.

## Evidence sources

- https://github.com/IBM/mcp-context-forge/tree/6004d236479c12ed2571d9bf9dc5cc20bf3aead7
- https://github.com/IBM/mcp-context-forge/blob/6004d236479c12ed2571d9bf9dc5cc20bf3aead7/docs/docs/architecture/index.md
- https://github.com/IBM/mcp-context-forge/blob/6004d236479c12ed2571d9bf9dc5cc20bf3aead7/mcpgateway/services/resource_service.py
- https://github.com/IBM/mcp-context-forge/blob/6004d236479c12ed2571d9bf9dc5cc20bf3aead7/mcpgateway/services/prompt_service.py
