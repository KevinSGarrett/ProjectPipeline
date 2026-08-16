# UPSTREAM-011 — atlassian/atlassian-mcp-server

- Disposition: `ADAPT_COMPONENT`
- Inspection state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Inspected revision: `94a30436435fb526a29f820f5f46250870eb75a0`
- License: `Apache-2.0`
- Candidate subsystem: `jira_steward`

## Purpose

Prefer the official Atlassian MCP server for an optional governed Jira/Confluence tool adapter; remote mutations remain policy-gated.

## Source-level paths reviewed

- `README.md`
- `skills/spec-to-backlog/SKILL.md`

## Integration decision

Prefer the official Atlassian MCP server for an optional governed Jira/Confluence tool adapter; remote mutations remain policy-gated.

## Security / portability / maintenance

- Security: Requires focused threat/dependency review before activation or source adaptation.
- Portability: Compatibility with Windows-first and offline/degraded profiles must be qualified before activation.
- Maintenance: Current metadata review does not replace release-pinning and maintenance qualification.

## Evidence sources

- https://github.com/atlassian/atlassian-mcp-server
- https://github.com/atlassian/atlassian-mcp-server/blob/94a30436435fb526a29f820f5f46250870eb75a0/README.md
- https://github.com/atlassian/atlassian-mcp-server/blob/94a30436435fb526a29f820f5f46250870eb75a0/skills/spec-to-backlog/SKILL.md

No upstream source is incorporated by this review. Any future adaptation requires the bounded source-incorporation gate.
