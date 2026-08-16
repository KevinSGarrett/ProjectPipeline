# UPSTREAM-041 — github/github-mcp-server

- Disposition: `ADAPT_COMPONENT`
- Inspection state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Inspected revision: `0ea1f775a7c73eff1bd2e25904d01136756bbfe2`
- License: `MIT`
- Candidate subsystem: `github_steward`

## Purpose

Implement an optional official GitHub MCP adapter/toolset profile while preserving Repository Steward write policy.

## Source-level paths reviewed

- `internal/ghmcp/server.go`

## Integration decision

Implement an optional official GitHub MCP adapter/toolset profile while preserving Repository Steward write policy.

## Security / portability / maintenance

- Security: Requires focused threat/dependency review before activation or source adaptation.
- Portability: Compatibility with Windows-first and offline/degraded profiles must be qualified before activation.
- Maintenance: Current metadata review does not replace release-pinning and maintenance qualification.

## Evidence sources

- https://github.com/github/github-mcp-server
- https://github.com/github/github-mcp-server/blob/0ea1f775a7c73eff1bd2e25904d01136756bbfe2/internal/ghmcp/server.go

No upstream source is incorporated by this review. Any future adaptation requires the bounded source-incorporation gate.
