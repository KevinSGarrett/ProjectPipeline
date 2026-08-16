# UPSTREAM-073 — openai/codex Integration Review

- License: `Apache-2.0`
- Inspected revision: `85fc4def358b7df21883e72ae8dda43a0f572f32`
- Candidate subsystem: `agent_router`
- Review state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Integration outcome: `OPTIONAL_ADAPTER_IMPLEMENTED` or `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- Live qualification: `NOT_LIVE_VERIFIED`

## Source areas inspected

- `codex-rs/exec/src/cli.rs`
- `codex-rs/utils/cli/src/shared_options.rs`
- `codex-rs/utils/cli/src/sandbox_mode_cli_arg.rs`

## Useful concepts

- non-interactive JSONL execution
- explicit sandbox modes
- approval-aware workspace mutation
- ephemeral execution

## Integration decision

- Use codex exec as an optional worker behind Project Pipeline action-intent and network gates.

## Engineering findings

- Architecture: Keep sandbox and approval policy outside the worker; use machine-readable event output and ephemeral runs.
- Security: Dangerous approval/sandbox bypass flags exist upstream and are prohibited by the Project Pipeline adapter.
- Portability: Codex CLI installation is external; adapter uses argv lists and no shell.
- Maintenance: CLI flags require version qualification at activation time.
- Maturity: Active production-grade CLI with current upstream development.
- Compatibility: Good fit behind the worker adapter boundary; Project Pipeline remains deterministic authority.
- Dependency implications: External codex CLI; no mandatory Python dependency.

## Evidence

- `GitHub:openai/codex@85fc4def358b7df21883e72ae8dda43a0f572f32`
- `codex-rs/exec/src/cli.rs`
- `codex-rs/utils/cli/src/shared_options.rs`
