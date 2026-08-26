# Upstream Reuse Engineering Policy

Project Pipeline treats the supplied upstream repository catalog as an implementation input. A catalog entry is not considered integrated merely because it was reviewed or selected.

## Required decision sequence

Before implementing a commodity capability:

1. identify relevant catalog repositories;
2. inspect the highest-value source, tests, release, and license surfaces;
3. record a disposition and revision;
4. prefer direct dependency use or a replaceable adapter when that preserves Project Pipeline authority;
5. use bounded source adaptation only after a separate adaptation review;
6. record actual use in the private maintainer evidence ledger;
7. add behavioral tests and rollback guidance.

The permanent upstream report exposes both architectural disposition and actual use state.

## Actual-use states

- `ACTIVE_RUNTIME` — dependency is in the active runtime path.
- `OPTIONAL_ADAPTER_IMPLEMENTED` — the adapter is implemented and tested but the external dependency/service may be unavailable.
- `EXTERNAL_CLI_ADAPTER_IMPLEMENTED` — a reviewed external executable is integrated through fixed arguments and Project Pipeline approval controls.
- `INCORPORATED_ASSET` — a bounded reviewed upstream asset is incorporated and used by project code.
- `SELECTED_NOT_ACTIVATED` — selected architecture candidate with no active integration claim.
- `FUTURE_SUBSYSTEM_BOUNDARY` — reserved for a later subsystem and not represented as active.

## Source adaptation

Source adaptation is denied by default. An approved bounded adaptation must have a private maintainer record containing the exact upstream revision and source path, ProjectPipeline path and hash, license, notice location, adaptation purpose, and behavioral tests.

The adaptation must be small and purposeful. Project Pipeline does not wholesale vendor a repository merely because its license permits copying.

## Authority boundary

Upstream software may perform commodity mechanics such as graph algorithms, optimization, worktree handling, provider transport, tool gateway lifecycle, or instrumentation. It does not own project state, task intent, scope, policy, completion, evidence, approval, or irreversible external mutation.
