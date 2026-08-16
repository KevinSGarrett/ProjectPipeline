# UPSTREAM-102 — SWE-agent/SWE-ReX

- Disposition: `ADAPT_COMPONENT`
- Inspection state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Inspected revision: `5c995c365dfb1fd5bc56fda688be5d8538f9931f`
- License: `MIT`
- Candidate subsystem: `worker_runtime`

## Purpose

Prioritize SWE-ReX as the sandboxed local/remote worker execution adapter because it separates agent logic from infrastructure.

## Source-level paths reviewed

- `README.md`
- `src/`
- `tests/`

## Integration decision

Prioritize SWE-ReX as the sandboxed local/remote worker execution adapter because it separates agent logic from infrastructure.

## Security / portability / maintenance

- Security: Requires focused threat/dependency review before activation or source adaptation.
- Portability: Compatibility with Windows-first and offline/degraded profiles must be qualified before activation.
- Maintenance: Current metadata review does not replace release-pinning and maintenance qualification.

## Evidence sources

- https://github.com/SWE-agent/SWE-ReX

No upstream source is incorporated by this review. Any future adaptation requires the bounded source-incorporation gate.
