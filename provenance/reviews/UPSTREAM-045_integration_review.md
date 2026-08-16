# UPSTREAM-045 — google-gemini/gemini-cli Integration Review

- License: `Apache-2.0`
- Inspected revision: `2a87e7be103308b8734246097ba723cc7deb4122`
- Candidate subsystem: `agent_router`
- Review state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Integration outcome: `OPTIONAL_ADAPTER_IMPLEMENTED` or `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- Live qualification: `NOT_LIVE_VERIFIED`

## Source areas inspected

- `docs/cli/headless.md`
- `docs/cli/cli-reference.md`

## Useful concepts

- headless execution
- stream-json output
- sandbox mode
- plan/auto_edit approval modes

## Integration decision

- Use Gemini CLI as an optional worker with plan mode for read-only work and auto_edit only after Project Pipeline approval.

## Engineering findings

- Architecture: Keep CLI execution headless and machine-readable; never use yolo mode.
- Security: The upstream yolo mode bypasses normal approvals and is prohibited by Project Pipeline.
- Portability: External Node-based CLI; adapter has no shell dependency.
- Maintenance: Headless output and approval modes must be version-qualified.
- Maturity: Active Google CLI with frequent releases and CI.
- Compatibility: Good optional worker boundary for provider diversity.
- Dependency implications: External gemini executable; credentials remain runtime secret references.

## Evidence

- `GitHub:google-gemini/gemini-cli@2a87e7be103308b8734246097ba723cc7deb4122`
- `docs/cli/headless.md`
- `docs/cli/cli-reference.md`
