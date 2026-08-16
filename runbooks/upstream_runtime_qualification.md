# Upstream runtime qualification runbook

Use this runbook when activating an implemented upstream adapter in a real Project Pipeline environment.

1. Identify the upstream ID and confirm its terminal disposition and implemented usage record.
2. Read the exact source review and `provenance/p0_convergence.json` record.
3. Pin the intended package version, executable release, container digest, or service API revision. Do not install an unqualified floating `latest` dependency.
4. Verify license and required notices. Source adaptation requires the separate bounded-incorporation record.
5. Run applicable secret, vulnerability, CI-security, and provenance checks before activation.
6. Confirm required secrets are provided by secret references rather than repository files.
7. For networked/provider tools, confirm egress and spend authorization.
8. For mutating workers or MCP tools, confirm the owning ActionIntent/Steward authority is enforced.
9. Run the adapter's contract tests plus one bounded live qualification scenario.
10. Record the exact version/digest, environment, evidence, and rollback/removal procedure. Only then promote the usage record's live-verification state.

Failure to qualify an optional tool must not block unrelated Project Pipeline work; keep the adapter implemented and mark only the unavailable live verification accurately.
