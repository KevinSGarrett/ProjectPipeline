# UPSTREAM-029 — docker/mcp-gateway

- **Canonical URL:** `https://github.com/docker/mcp-gateway`
- **Inspected revision:** `24b028f4f9aac85ce1a1057c5e8d739836e7c18d`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MIT`
- **Disposition:** `ADOPT_DEPENDENCY`
- **Dependency activation eligible:** `true`
- **Source incorporation approved:** `false`

## Project Pipeline role

Selected MCP server lifecycle and isolation implementation behind GovernedToolPort.

## Useful concepts

- container-isolated MCP servers
- profiles, discovery, OAuth, secrets, and tool allowlists
- logging and call tracing

## Reviewed files and surfaces

- `README.md`
- `LICENSE`

## Integration boundary

- Run approved MCP servers through profile-specific allowlists
- translate discovered tools into internal capabilities and policy checks

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

MCP lifecycle can be reused, but the Project Pipeline registry remains the authority for tool identity and permission.

## Risk and operability review

- **Security:** ['Docker socket and catalog trust are high-risk boundaries', 'disable ambient host privileges and unapproved tools']
- **Portability:** ['Strong Docker Desktop and container fit', 'requires Docker-compatible runtime']
- **Maintenance:** ['Pin gateway and catalog references; review OCI provenance']
- **Maturity:** `Active official Docker implementation.`
- **Compatibility:** `DIRECT_DEPENDENCY_BEHIND_TOOL_PORT`

## License and provenance boundary

Dependency activation and source incorporation are separate. Preserve notices, pin the activated artifact, and comply with provenance and distribution policy.

**Disposition rationale:** Approved for bounded dependency use in the recorded subsystem behind Project Pipeline contracts. Activation still requires a pinned release or digest, security and compatibility evidence, notices, tests, and rollback. Source incorporation is not approved.

**Dependency implications:** Eligible only within the recorded adapter/profile boundary after version locking, vulnerability review, contract tests, operational qualification, SBOM/notice generation, and rollback evidence.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `SRC-016:L001778-L001783`
- `github:docker/mcp-gateway@24b028f4:README.md`
- `github:docker/mcp-gateway:LICENSE`

## Project Pipeline disposition after source chronology review

- Source strategy: `SOURCE_SELECTED_TARGET`
- Disposition: `ADOPT_DEPENDENCY`
- Dependency activation eligible: `true`
- Source incorporation approved: `false`
- Rationale: Docker MCP Gateway is selected for bounded dependency use by the latest source-aligned architecture. Activation remains version-locked, policy-gated, compatibility-tested, and reversible; source incorporation is not approved.
## Project Pipeline integration state

Project Pipeline now implements a secure-default Docker MCP Gateway command adapter and uses a bounded, provenance-recorded data contract derived from the reviewed gateway run reference.
