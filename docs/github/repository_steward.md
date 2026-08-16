# Repository Steward

Project Pipeline separates **repository authority** from worker implementation. The Repository Steward observes Git state with fixed, non-shell commands; models branches and worktrees; owns resource-conflict decisions; evaluates pull requests; and proposes cleanup without erasing work in progress.

## Local Git boundary

`LocalGitRepository` executes only predefined Git subcommands with `shell=False`. It does not execute repository scripts, hooks as application logic, package managers, build tools, or content discovered from files. Inspection returns a typed repository snapshot, local branches, registered worktrees, dirty paths, remotes, upstream divergence, and merge ancestry.

Default-branch implementation and detached HEAD state are blocking Branch Guardian findings. Dirty work is preserved: it may remain workable, but cleanup is disabled until the work is deliberately handled.

## Worktrees and ownership

Worktree creation/removal is dry-run unless explicitly applied. Removal of a dirty worktree fails closed. Resource claims can cover files, directories, schemas, databases, ports, environments, or whole repositories. Overlapping active path claims owned by different tasks are rejected.

## GitHub boundary

`GitHubRemotePort` isolates provider operations. `GitHubRestAdapter` implements the GitHub REST request/response contract; `MockGitHubAdapter` is deterministic test infrastructure. The mock is never evidence of live GitHub behavior.

Read operations can be retried when the error is known transient. Remote mutations are not blindly retried after an ambiguous transport failure. Such operations are persisted as `UNKNOWN_OUTCOME` so recovery can inspect GitHub before attempting another write.

## Merge Gate

A merge is blocked when the pull request is closed, draft, conflicting, at an unexpected head SHA, missing a required check, has an incomplete or failed required check, lacks required approvals, or has a current changes-requested review. The gate is an authorization prerequisite, not a substitute for the broader Completion Gate.

## CLI examples

```text
project-pipeline repository inspect --repository-root <path>
project-pipeline repository guardian --repository-root <path>
project-pipeline repository create-branch --repository-root <path> --branch feature/PP-TASK-000001
project-pipeline github merge-gate --repository-root <path> --repository-slug owner/repo --pull-number 12
project-pipeline github merge --repository-root <path> --repository-slug owner/repo --pull-number 12
```

The last command is dry-run unless `--apply --approve --authorization-id ...` are supplied. Live GitHub writes also require runtime external-write policy to be `REQUIRE_APPROVAL` and a resolvable GitHub token secret reference.
