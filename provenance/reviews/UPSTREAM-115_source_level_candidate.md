# UPSTREAM-115 — yamadashy/repomix

- Disposition: `ADAPT_COMPONENT`
- Inspection state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Inspected revision: `e3b15a406ed78d8a463620a032a059ce911bfc0e`
- License: `MIT`
- Candidate subsystem: `context_compiler`

## Purpose

Prioritize a Repomix CLI/MCP adapter for context packing, filtering, token-aware repository compression, and source minimization.

## Source-level paths reviewed

- `src/core/packager.ts`
- `src/mcp/tools/packCodebaseTool.ts`
- `website/client/src/en/guide/security.md`

## Integration decision

Prioritize a Repomix CLI/MCP adapter for context packing, filtering, token-aware repository compression, and source minimization.

## Security / portability / maintenance

- Security: Requires focused threat/dependency review before activation or source adaptation.
- Portability: Compatibility with Windows-first and offline/degraded profiles must be qualified before activation.
- Maintenance: Current metadata review does not replace release-pinning and maintenance qualification.

## Evidence sources

- https://github.com/yamadashy/repomix
- https://github.com/yamadashy/repomix/blob/e3b15a406ed78d8a463620a032a059ce911bfc0e/src/core/packager.ts
- https://github.com/yamadashy/repomix/blob/e3b15a406ed78d8a463620a032a059ce911bfc0e/src/mcp/tools/packCodebaseTool.ts
- https://github.com/yamadashy/repomix/blob/e3b15a406ed78d8a463620a032a059ce911bfc0e/website/client/src/en/guide/security.md

No upstream source is incorporated by this review. Any future adaptation requires the bounded source-incorporation gate.
